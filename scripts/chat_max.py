"""CLI alternativo: usa la auth de Claude Code (Max / Pro) en vez de API key.

A diferencia de scripts/chat.py:
- No requiere ANTHROPIC_API_KEY.
- Requiere `claude` (Claude Code CLI) instalado y logueado.
- El consumo va contra tu suscripción Max/Pro, no contra billing de API.

Reusa `app/agent_claude_code.py` — el mismo módulo que sirve el web demo.

Uso:
    python scripts/chat_max.py                     # interactivo
    python scripts/chat_max.py "¿Tenés Borges?"   # one-shot
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import agent_claude_code  # noqa: E402


BANNER = """
La Librería · asistente (modo Claude Max)
Escribí tu mensaje. Ctrl+C o 'salir' para terminar.
"""


async def chat_interactive() -> None:
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    try:
        print(BANNER)
        while True:
            try:
                msg = input("Vos: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not msg:
                continue
            if msg.lower() in ("salir", "exit", "quit"):
                break
            reply = await agent_claude_code.reply(session_id, msg)
            print(f"\nBot: {reply}\n")
    finally:
        await agent_claude_code.close(session_id)


async def chat_one_shot(msg: str) -> None:
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    try:
        print(await agent_claude_code.reply(session_id, msg))
    finally:
        await agent_claude_code.close(session_id)


def main() -> None:
    if len(sys.argv) > 1:
        asyncio.run(chat_one_shot(" ".join(sys.argv[1:])))
    else:
        asyncio.run(chat_interactive())


if __name__ == "__main__":
    main()
