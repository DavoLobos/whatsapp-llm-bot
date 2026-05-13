"""Per-user conversation history.

In-process dict keyed by phone number. Not production-ready — swap for a
durable store (Redis, Postgres) before deploying to multiple workers.
"""

from __future__ import annotations

from threading import Lock

from .config import settings

_HISTORY: dict[str, list[dict]] = {}
_LOCK = Lock()


def get_history(user_id: str) -> list[dict]:
    """Return a copy of the user's conversation history."""
    with _LOCK:
        return list(_HISTORY.get(user_id, []))


def append_turn(user_id: str, user_message: str, assistant_message: str) -> None:
    """Append a user/assistant turn to the user's history and prune to the configured cap."""
    with _LOCK:
        history = _HISTORY.setdefault(user_id, [])
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_message})
        excess = len(history) - settings.max_history_messages
        if excess > 0:
            # Drop in pairs to keep user/assistant alternation valid.
            drop = excess if excess % 2 == 0 else excess + 1
            del history[:drop]


def reset(user_id: str) -> None:
    """Clear a user's conversation history."""
    with _LOCK:
        _HISTORY.pop(user_id, None)
