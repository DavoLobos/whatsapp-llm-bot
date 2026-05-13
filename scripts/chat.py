"""CLI para probar el bot sin WhatsApp.

Sólo necesita ANTHROPIC_API_KEY en el entorno (o en .env). Las variables de
WhatsApp se ignoran en este modo — el script las setea con valores dummy
porque app.config las requiere al importar.

Uso:
    python scripts/chat.py                       # modo interactivo
    python scripts/chat.py "¿qué libros de Borges tenés?"   # one-shot
"""

from __future__ import annotations

import os
import sys

# Setear valores dummy ANTES de importar app.* — config.py los exige.
os.environ.setdefault("WHATSAPP_TOKEN", "cli-not-used")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "cli-not-used")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "cli-not-used")
os.environ.setdefault("WHATSAPP_APP_SECRET", "cli-not-used")

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit(
        "Falta ANTHROPIC_API_KEY. Conseguí una en https://console.anthropic.com\n"
        "y exportala antes de correr el script:\n"
        "  Windows PowerShell: $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
        "  Bash/macOS:         export ANTHROPIC_API_KEY=sk-ant-..."
    )

# Importar después del env setup.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import agent  # noqa: E402


BANNER = """
La Librería · asistente
Escribí tu mensaje. Ctrl+C o 'salir' para terminar.
"""


def chat_interactive() -> None:
    history: list[dict] = []
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
        reply = agent.reply(history, msg)
        print(f"\nBot: {reply}\n")
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": reply})


def chat_one_shot(msg: str) -> None:
    print(agent.reply([], msg))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        chat_one_shot(" ".join(sys.argv[1:]))
    else:
        chat_interactive()
