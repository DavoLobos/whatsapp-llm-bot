"""In-memory bookstore catalog loaded from a JSON file at boot.

Swap this module's implementation for a database query in production —
the public surface (`search`, `get`, `similar`, `summary`) is what the
agent's tools and system prompt depend on.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Final

from pydantic import BaseModel

_DATA_FILE: Final = Path(__file__).parent / "data" / "books.json"


class Book(BaseModel):
    id: str
    title: str
    author: str
    genre: str
    price: int
    stock: int
    summary: str


def _load() -> dict[str, Book]:
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return {b["id"]: Book.model_validate(b) for b in raw}


_BOOKS: Final[dict[str, Book]] = _load()


def all_books() -> list[Book]:
    return list(_BOOKS.values())


def get(book_id: str) -> Book | None:
    return _BOOKS.get(book_id)


def search(query: str, limit: int = 5) -> list[Book]:
    """Case-insensitive substring match across title, author, and genre."""
    needle = query.strip().lower()
    if not needle:
        return []
    matches = [
        b
        for b in _BOOKS.values()
        if needle in b.title.lower()
        or needle in b.author.lower()
        or needle in b.genre.lower()
    ]
    matches.sort(key=lambda b: (b.stock == 0, b.title))
    return matches[:limit]


def similar(book_id: str, limit: int = 3) -> list[Book]:
    """Return up to `limit` books that share the same genre, excluding the given book."""
    base = _BOOKS.get(book_id)
    if base is None:
        return []
    related = [
        b for b in _BOOKS.values() if b.id != base.id and b.genre == base.genre
    ]
    related.sort(key=lambda b: (b.stock == 0, b.title))
    return related[:limit]


def summary() -> str:
    """Compact, model-friendly summary of the catalog for the system prompt.

    Stable across requests — safe to include inside a cached system prompt block.
    """
    genres = Counter(b.genre for b in _BOOKS.values()).most_common()
    genre_lines = "\n".join(f"- {g} ({n} títulos)" for g, n in genres)
    total = len(_BOOKS)
    in_stock = sum(1 for b in _BOOKS.values() if b.stock > 0)
    return (
        f"La librería tiene {total} títulos en catálogo ({in_stock} con stock disponible).\n\n"
        f"Géneros disponibles:\n{genre_lines}"
    )
