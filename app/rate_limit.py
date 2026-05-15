"""In-memory rate limiting para el web demo.

Dos caps:
- Por sesión: cada visitante (cookie / localStorage UUID) tiene N mensajes.
- Global diario: total de mensajes servidos hoy por toda la instancia.

Sin Redis ni nada externo — válido para un demo de portfolio. Para algo
con tráfico real, swap por Redis + sliding window.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date


PER_SESSION_CAP = 10
GLOBAL_DAILY_CAP = 200


@dataclass
class _State:
    session_counts: dict[str, int] = field(default_factory=dict)
    global_count: int = 0
    current_day: date = field(default_factory=date.today)


_state = _State()
_lock = asyncio.Lock()


@dataclass
class CheckResult:
    allowed: bool
    reason: str | None = None
    remaining_in_session: int = 0


async def check_and_consume(session_id: str) -> CheckResult:
    """Atomically check both caps and, if both pass, consume one message."""
    async with _lock:
        today = date.today()
        if today != _state.current_day:
            _state.current_day = today
            _state.global_count = 0
            _state.session_counts.clear()

        if _state.global_count >= GLOBAL_DAILY_CAP:
            return CheckResult(
                allowed=False,
                reason=(
                    "La demo alcanzó su cupo diario de mensajes. "
                    "Volvé mañana o mirá el código en GitHub."
                ),
            )

        used = _state.session_counts.get(session_id, 0)
        if used >= PER_SESSION_CAP:
            return CheckResult(
                allowed=False,
                reason=(
                    f"Llegaste al límite de {PER_SESSION_CAP} mensajes en esta sesión "
                    "(la demo es acotada para no agotar el cupo). Refrescá para empezar de nuevo."
                ),
            )

        _state.session_counts[session_id] = used + 1
        _state.global_count += 1
        return CheckResult(
            allowed=True,
            remaining_in_session=PER_SESSION_CAP - (used + 1),
        )


async def snapshot() -> dict:
    """Read-only status for healthz / debugging."""
    async with _lock:
        return {
            "day": _state.current_day.isoformat(),
            "global_used": _state.global_count,
            "global_cap": GLOBAL_DAILY_CAP,
            "active_sessions": len(_state.session_counts),
            "per_session_cap": PER_SESSION_CAP,
        }
