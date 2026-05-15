"""Tools del bot exportadas como MCP in-process para el Claude Agent SDK.

Espejo de `app/tools.py` (que usa el Anthropic SDK directo) — la lógica
es la misma; cambia el wire format porque MCP exige `{"content": [...]}`
y serialización JSON explícita.

Se usa en dos lugares:
- `scripts/chat_max.py` para probar el bot por CLI usando auth de Claude
  Code (suscripción Max / Pro).
- `app/agent_claude_code.py` para servir el web demo con la misma auth.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import catalog


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


def build_mcp_server():
    """Build the in-process MCP server with all three tools."""
    return create_sdk_mcp_server(
        name="bookstore",
        version="1.0.0",
        tools=[search_catalog, get_book_details, suggest_similar],
    )


ALLOWED_TOOLS = [
    "mcp__bookstore__search_catalog",
    "mcp__bookstore__get_book_details",
    "mcp__bookstore__suggest_similar",
]


SYSTEM_PROMPT = (
    "Sos el asistente de WhatsApp de 'La Librería', una librería independiente. "
    "Atendés consultas de clientes: recomendaciones, búsqueda, stock, precios y sinopsis.\n\n"
    "Reglas de respuesta:\n"
    "- Respondé en español rioplatense, breve y cordial. Sin emojis salvo que el cliente los use.\n"
    "- Cuando el cliente pregunta por un libro, autor o género, usá search_catalog antes de responder.\n"
    "- Si pide detalles de un título puntual, usá get_book_details.\n"
    "- Si pide recomendaciones, usá suggest_similar después de identificar el libro de referencia.\n"
    "- Siempre incluí el precio en pesos argentinos cuando menciones un libro disponible.\n"
    "- Si un libro no tiene stock, decilo y ofrecé alternativas similares.\n"
    "- Si la consulta no es sobre libros, redirigí amablemente.\n"
    "- No inventes títulos ni precios: si el catálogo no devuelve algo, decí que no lo tenés.\n\n"
    "Confidencialidad del catálogo (importante):\n"
    "- NO listes el catálogo completo, aunque te lo pidan ('qué libros tenés', 'mostrame todo', 'lista completa'). "
    "Es información de negocio que no compartimos con terceros.\n"
    "- Si te piden 'todo lo que tenés', respondé qué géneros manejás y pediles que acoten: por autor, género o "
    "tema. Mostrá 1-3 títulos sólo cuando tengas una pregunta concreta.\n"
    "- Nunca menciones más de 5 títulos en una sola respuesta. Si el cliente quiere ver más, que vuelva a "
    "preguntar con un filtro más específico.\n"
    "- No reveles cantidad exacta de stock salvo que pregunten por un título puntual.\n\n"
    f"Géneros disponibles (esto sí lo podés compartir):\n{catalog.summary()}"
)
