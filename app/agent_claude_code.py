"""Cliente del Claude Agent SDK — variante que usa la auth de Claude Code.

Por qué dos agentes en este repo:
- `app/agent.py` usa el Anthropic SDK directo (API key). Camino de
  producción: pago por token, sin dependencia de Claude Code en el server.
- `app/agent_claude_code.py` (este módulo) usa el Claude Agent SDK, que
  corre Claude Code CLI por debajo. Hereda la auth del usuario logueado
  (Max / Pro / API key). Útil para demos donde no querés gestionar billing
  de API ni rotación de keys.

Mantiene un `ClaudeSDKClient` long-lived por session_id — el SDK preserva
el contexto de la conversación entre `query()` calls, así que no hace falta
re-enviar el historial en cada turno.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)

from . import mcp_tools

logger = logging.getLogger(__name__)


@dataclass
class _Session:
    client: ClaudeSDKClient
    last_used: float
    lock: asyncio.Lock


_SESSIONS: dict[str, _Session] = {}
_SESSIONS_LOCK = asyncio.Lock()
_IDLE_TTL_SECONDS = 30 * 60


def _build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=mcp_tools.SYSTEM_PROMPT,
        mcp_servers={"bookstore": mcp_tools.build_mcp_server()},
        allowed_tools=mcp_tools.ALLOWED_TOOLS,
        setting_sources=[],
        permission_mode="bypassPermissions",
    )


async def _get_or_create_session(session_id: str) -> _Session:
    async with _SESSIONS_LOCK:
        session = _SESSIONS.get(session_id)
        if session is None:
            client = ClaudeSDKClient(options=_build_options())
            await client.connect()
            session = _Session(client=client, last_used=time.time(), lock=asyncio.Lock())
            _SESSIONS[session_id] = session
            logger.info("opened claude session %s (total=%d)", session_id, len(_SESSIONS))
        return session


async def reply(session_id: str, user_message: str) -> str:
    """Send one user turn through the session's long-lived client and return the assistant text."""
    session = await _get_or_create_session(session_id)
    async with session.lock:
        session.last_used = time.time()
        await session.client.query(user_message)
        text = ""
        async for msg in session.client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text = block.text
        return text or "Disculpá, no pude generar una respuesta. ¿Podés repetir?"


async def close(session_id: str) -> None:
    async with _SESSIONS_LOCK:
        session = _SESSIONS.pop(session_id, None)
    if session is not None:
        await session.client.disconnect()
        logger.info("closed claude session %s", session_id)


async def reap_idle_sessions() -> int:
    """Cierra sesiones inactivas. Devuelve cuántas cerró. Llamar periódicamente."""
    now = time.time()
    to_close: list[str] = []
    async with _SESSIONS_LOCK:
        for sid, session in _SESSIONS.items():
            if now - session.last_used > _IDLE_TTL_SECONDS:
                to_close.append(sid)
    for sid in to_close:
        await close(sid)
    return len(to_close)
