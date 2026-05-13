"""Tools exposed to Claude.

Declared as typed Python functions with `@beta_tool` — the Anthropic SDK
generates JSON schemas from the signature and docstring automatically.
The tool runner executes these whenever Claude requests them.
"""

from __future__ import annotations

from anthropic import beta_tool

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


@beta_tool
def search_catalog(query: str, max_results: int = 5) -> list[dict]:
    """Buscar libros en el catálogo de la librería.

    Hace match contra título, autor y género (case-insensitive).
    Usalo cuando el usuario pregunta por un libro, autor, o género.

    Args:
        query: Texto libre a buscar (título, autor, o género).
        max_results: Cantidad máxima de resultados a devolver (1-10).
    """
    results = catalog.search(query, limit=max(1, min(max_results, 10)))
    return [_serialize(b) for b in results]


@beta_tool
def get_book_details(book_id: str) -> dict:
    """Traer todos los detalles de un libro: sinopsis, stock exacto, precio.

    Usalo después de un search cuando el usuario quiere saber más de un título
    específico (sinopsis, disponibilidad real, etc).

    Args:
        book_id: ID del libro (devuelto por search_catalog, formato "B###").
    """
    book = catalog.get(book_id)
    if book is None:
        return {"error": f"No existe ningún libro con id '{book_id}'."}
    return {**_serialize(book), "summary": book.summary}


@beta_tool
def suggest_similar(book_id: str, max_results: int = 3) -> list[dict]:
    """Sugerir libros similares a uno dado (mismo género).

    Usalo cuando el usuario pregunta por recomendaciones o "qué más tenés
    parecido a X".

    Args:
        book_id: ID del libro base (formato "B###").
        max_results: Cantidad máxima de sugerencias (1-5).
    """
    results = catalog.similar(book_id, limit=max(1, min(max_results, 5)))
    return [_serialize(b) for b in results]


TOOLS = [search_catalog, get_book_details, suggest_similar]
