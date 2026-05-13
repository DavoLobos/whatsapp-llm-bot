"""Claude integration.

Single entry point: `reply(history, user_message) -> assistant_text`.

Highlights:
- Model: Claude Opus 4.7 (`claude-opus-4-7`).
- Adaptive thinking: Claude decides per-message how much to think.
- Prompt caching: the system prompt (role + catalog summary) is cached so
  repeated turns across all users pay ~10% input cost on the prefix.
- Tool use: handled by the SDK's beta tool runner — no hand-rolled loop.
"""

from __future__ import annotations

import logging
from typing import Final

import anthropic

from . import catalog
from .config import settings
from .tools import TOOLS

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _build_system_prompt() -> list[dict]:
    """Build the system prompt as a single cacheable text block.

    Everything in here is stable across requests. Anything user-specific
    must live in the `messages` array, after this cache breakpoint.
    """
    body = (
        "Sos el asistente de WhatsApp de 'La Librería', una librería independiente. "
        "Atendés consultas de clientes: recomendaciones, búsqueda de títulos, stock, "
        "precios y sinopsis.\n\n"
        "Reglas:\n"
        "- Respondé en español rioplatense, breve y cordial. Sin emojis salvo que el cliente los use.\n"
        "- Cuando el cliente pregunta por un libro, autor o género, usá search_catalog antes de responder.\n"
        "- Si el cliente pide detalles de un título puntual, usá get_book_details.\n"
        "- Si pide recomendaciones, usá suggest_similar después de identificar el libro de referencia.\n"
        "- Siempre incluí el precio en pesos argentinos cuando menciones un libro disponible.\n"
        "- Si un libro no tiene stock, decilo claramente y ofrecé alternativas similares.\n"
        "- Si la consulta no es sobre libros (clima, política, otros temas), redirigí amablemente.\n"
        "- No inventes títulos ni precios: si el catálogo no devuelve algo, decí que no lo tenés.\n\n"
        f"Contexto del catálogo:\n{catalog.summary()}"
    )
    return [
        {
            "type": "text",
            "text": body,
            "cache_control": {"type": "ephemeral"},
        }
    ]


_SYSTEM: Final = _build_system_prompt()


def reply(history: list[dict], user_message: str) -> str:
    """Generate an assistant reply for one user turn.

    `history` is the per-user conversation so far (alternating user/assistant
    messages). `user_message` is the new turn — it is appended internally and
    is the responsibility of the caller to persist together with the reply.
    """
    messages = [*history, {"role": "user", "content": user_message}]

    runner = _client.beta.messages.tool_runner(
        model=settings.model_id,
        max_tokens=2048,
        system=_SYSTEM,
        tools=TOOLS,
        messages=messages,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
    )

    final_text: str | None = None
    for message in runner:
        usage = message.usage
        logger.info(
            "claude turn: input=%d cache_read=%d cache_write=%d output=%d stop=%s",
            usage.input_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
            usage.output_tokens,
            message.stop_reason,
        )
        for block in message.content:
            if block.type == "text" and block.text.strip():
                final_text = block.text

    if not final_text:
        return "Disculpá, tuve un problema procesando tu mensaje. ¿Podés repetirlo?"
    return final_text
