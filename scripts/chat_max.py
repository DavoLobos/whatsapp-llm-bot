"""CLI alternativo: usa la auth de Claude Code (Max / Pro) en vez de API key.

A diferencia de scripts/chat.py:
- No requiere ANTHROPIC_API_KEY.
- Requiere `claude` (Claude Code CLI) instalado y logueado.
- El consumo va contra tu suscripción Max/Pro, no contra billing de API.

Re-implementa la lógica del bot (system prompt + 3 tools) usando el Claude
Agent SDK con tools in-process (SDK MCP). Es un duplicado intencional de
app/agent.py para mantener el módulo principal con el shape de producción
(Anthropic SDK directo, listo para deploy con API key).

Uso:
    python scripts/chat_max.py                       # interactivo
    python scripts/chat_max.py "¿Tenés Borges?"     # one-shot
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Annotated, Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import catalog  # noqa: E402


BANNER = """
La Librería · asistente (modo Claude Max)
Escribí tu mensaje. Ctrl+C o 'salir' para terminar.
"""


def _serialize(book: catalog.Book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "genre": book.genre,
        "price_ars": book.price,
        "in_stock": book.stock > 0,
        "stock": book.stock,
    }


@tool(
    "search_catalog",
    "Buscar libros del catálogo por título, autor o género. Usalo cuando el cliente "
    "pregunta por un libro, autor o género específico.",
    {
        "query": Annotated[str, "Texto libre (título, autor o género)."],
        "max_results": Annotated[int, "Cantidad máxima de resultados (1-10). Default: 5."],
    },
)
async def search_catalog(args: dict[str, Any]) -> dict:
    limit = max(1, min(int(args.get("max_results", 5)), 10))
    results = catalog.search(args["query"], limit=limit)
    payload = [_serialize(b) for b in results]
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


@tool(
    "get_book_details",
    "Traer sinopsis, stock exacto y precio de un libro específico (después de un search).",
    {"book_id": Annotated[str, "ID del libro (formato 'B###')."]},
)
async def get_book_details(args: dict[str, Any]) -> dict:
    book = catalog.get(args["book_id"])
    if book is None:
        err = {"error": f"No existe el libro '{args['book_id']}'."}
        return {"content": [{"type": "text", "text": json.dumps(err)}], "is_error": True}
    payload = {**_serialize(book), "summary": book.summary}
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


@tool(
    "suggest_similar",
    "Sugerir libros del mismo género que uno dado.",
    {
        "book_id": Annotated[str, "ID del libro base (formato 'B###')."],
        "max_results": Annotated[int, "Cantidad máxima de sugerencias (1-5). Default: 3."],
    },
)
async def suggest_similar(args: dict[str, Any]) -> dict:
    limit = max(1, min(int(args.get("max_results", 3)), 5))
    results = catalog.similar(args["book_id"], limit=limit)
    payload = [_serialize(b) for b in results]
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


SYSTEM_PROMPT = (
    "Sos el asistente de WhatsApp de 'La Librería', una librería independiente. "
    "Atendés consultas de clientes: recomendaciones, búsqueda, stock, precios y sinopsis.\n\n"
    "Reglas:\n"
    "- Respondé en español rioplatense, breve y cordial. Sin emojis salvo que el cliente los use.\n"
    "- Cuando el cliente pregunta por un libro, autor o género, usá search_catalog antes de responder.\n"
    "- Si pide detalles de un título puntual, usá get_book_details.\n"
    "- Si pide recomendaciones, usá suggest_similar después de identificar el libro de referencia.\n"
    "- Siempre incluí el precio en pesos argentinos cuando menciones un libro disponible.\n"
    "- Si un libro no tiene stock, decilo y ofrecé alternativas similares.\n"
    "- Si la consulta no es sobre libros, redirigí amablemente.\n"
    "- No inventes títulos ni precios: si el catálogo no devuelve algo, decí que no lo tenés.\n\n"
    f"Contexto del catálogo:\n{catalog.summary()}"
)


def _build_options() -> ClaudeAgentOptions:
    server = create_sdk_mcp_server(
        name="bookstore",
        version="1.0.0",
        tools=[search_catalog, get_book_details, suggest_similar],
    )
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"bookstore": server},
        allowed_tools=[
            "mcp__bookstore__search_catalog",
            "mcp__bookstore__get_book_details",
            "mcp__bookstore__suggest_similar",
        ],
        setting_sources=[],
        permission_mode="bypassPermissions",
    )


async def _read_final_text(client: ClaudeSDKClient) -> str:
    text = ""
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text = block.text
    return text or "(sin respuesta)"


async def chat_interactive() -> None:
    async with ClaudeSDKClient(_build_options()) as client:
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
            await client.query(msg)
            reply = await _read_final_text(client)
            print(f"\nBot: {reply}\n")


async def chat_one_shot(msg: str) -> None:
    async with ClaudeSDKClient(_build_options()) as client:
        await client.query(msg)
        print(await _read_final_text(client))


def main() -> None:
    if len(sys.argv) > 1:
        asyncio.run(chat_one_shot(" ".join(sys.argv[1:])))
    else:
        asyncio.run(chat_interactive())


if __name__ == "__main__":
    main()
