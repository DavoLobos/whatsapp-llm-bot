"""WhatsApp Cloud API client and webhook signature verification.

Two public functions:
- `verify_signature(raw_body, signature_header)`: validate Meta's X-Hub-Signature-256.
- `send_text(to, text)`: send a plain text message to a WhatsApp number.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Final

import httpx

from .config import settings

logger = logging.getLogger(__name__)

GRAPH_API_VERSION: Final = "v22.0"
_SEND_URL: Final = (
    f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.whatsapp_phone_number_id}/messages"
)


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's `X-Hub-Signature-256` header against the raw request body.

    Returns `True` if the signature matches the app secret. Constant-time compare.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


async def send_text(to: str, text: str) -> None:
    """Send a plain text WhatsApp message via Meta's Cloud API."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(_SEND_URL, json=payload, headers=headers)
    if response.status_code >= 400:
        logger.error("WhatsApp send failed: %s %s", response.status_code, response.text)
        response.raise_for_status()
