"""FastAPI entry point.

Two routes:
- GET  /webhook   Meta verification challenge.
- POST /webhook   Incoming WhatsApp events (text messages handled).

Everything else is delegated to dedicated modules:
- Signature verification + outgoing API: `whatsapp.py`
- Conversation state: `session.py`
- LLM reply: `agent.py`
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from . import agent, session, whatsapp
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="whatsapp-llm-bot", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "model": settings.model_id}


@app.get("/webhook", response_class=PlainTextResponse)
async def verify(request: Request) -> str:
    """Meta webhook verification handshake.

    See https://developers.facebook.com/docs/graph-api/webhooks/getting-started
    """
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
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not whatsapp.verify_signature(raw, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    payload = await request.json()
    for message in _iter_text_messages(payload):
        background.add_task(_handle_message, message["from"], message["text"])
    return {"status": "ok"}


def _iter_text_messages(payload: dict):
    """Yield {'from': str, 'text': str} for each text message in a webhook payload.

    Other message types (image, audio, location, status updates) are ignored.
    """
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                if msg.get("type") == "text":
                    yield {"from": msg["from"], "text": msg["text"]["body"]}


async def _handle_message(from_number: str, text: str) -> None:
    """End-to-end handling: load history, call Claude, persist turn, send reply."""
    try:
        history = session.get_history(from_number)
        # agent.reply is synchronous (the SDK call blocks) — run it off the event loop.
        reply_text = await asyncio.to_thread(agent.reply, history, text)
        session.append_turn(from_number, text, reply_text)
        await whatsapp.send_text(from_number, reply_text)
    except Exception:
        logger.exception("error handling message from %s", from_number)
