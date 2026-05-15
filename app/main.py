"""FastAPI entry point.

Three surfaces:

1. **Web demo** — `GET /` + `POST /chat`. Single-page chat that talks to the
   bot via the Claude Agent SDK (uses Claude Code auth, no API key billing).
   Rate-limited per session and globally.
2. **WhatsApp webhook** — `GET /webhook` (Meta verification) + `POST /webhook`
   (incoming messages). Uses the Anthropic SDK + API key path. Only mounted
   if WhatsApp credentials are configured.
3. **Healthcheck** — `GET /healthz`.

Everything else is delegated to dedicated modules.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import agent_claude_code, rate_limit
from .config import settings, whatsapp_configured

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="whatsapp-llm-bot", version="1.0.0")

_TEMPLATE = (Path(__file__).parent / "templates" / "chat.html").read_text(encoding="utf-8")


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "status": "ok",
        "model": settings.model_id,
        "whatsapp_enabled": whatsapp_configured(),
        "rate_limit": await rate_limit.snapshot(),
    }


# ---------------------------------------------------------------------------
# Web demo
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    message: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    reply: str
    remaining: int


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _TEMPLATE


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    check = await rate_limit.check_and_consume(payload.session_id)
    if not check.allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=check.reason)

    try:
        reply_text = await agent_claude_code.reply(payload.session_id, payload.message)
    except Exception:
        logger.exception("agent error for session %s", payload.session_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pude generar respuesta. Intentá de nuevo en un momento.",
        )

    return ChatResponse(reply=reply_text, remaining=check.remaining_in_session)


# ---------------------------------------------------------------------------
# WhatsApp webhook
# ---------------------------------------------------------------------------


@app.get("/webhook", response_class=PlainTextResponse)
async def verify(request: Request) -> str:
    """Meta webhook verification handshake.

    See https://developers.facebook.com/docs/graph-api/webhooks/getting-started
    """
    if not whatsapp_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="whatsapp disabled")

    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return challenge
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="verification failed")


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def incoming(request: Request, background: BackgroundTasks) -> dict:
    """Receive incoming WhatsApp events.

    Returns 200 immediately to satisfy Meta's retry policy, then processes
    the message in the background. Replies are sent via WhatsApp Cloud API.
    """
    if not whatsapp_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="whatsapp disabled")

    # Imports lazy: only needed when WhatsApp is wired up.
    from . import agent, session as wa_session, whatsapp

    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not whatsapp.verify_signature(raw, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    payload = await request.json()
    for message in _iter_text_messages(payload):
        background.add_task(_handle_whatsapp_message, message["from"], message["text"])
    return {"status": "ok"}


def _iter_text_messages(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                if msg.get("type") == "text":
                    yield {"from": msg["from"], "text": msg["text"]["body"]}


async def _handle_whatsapp_message(from_number: str, text: str) -> None:
    from . import agent, session as wa_session, whatsapp
    try:
        history = wa_session.get_history(from_number)
        reply_text = await asyncio.to_thread(agent.reply, history, text)
        wa_session.append_turn(from_number, text, reply_text)
        await whatsapp.send_text(from_number, reply_text)
    except Exception:
        logger.exception("error handling whatsapp message from %s", from_number)
