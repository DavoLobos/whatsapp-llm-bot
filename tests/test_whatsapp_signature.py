"""Signature-verification tests for the WhatsApp webhook.

Stubs the settings module so the test doesn't require a real Meta app secret.
"""

import hashlib
import hmac
import os

# Set required env vars BEFORE importing the app, so pydantic-settings is happy.
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("WHATSAPP_TOKEN", "test")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "test")
os.environ.setdefault("WHATSAPP_VERIFY_TOKEN", "test")
os.environ.setdefault("WHATSAPP_APP_SECRET", "supersecret")

from app import whatsapp  # noqa: E402


def _sign(body: bytes, secret: str = "supersecret") -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_signature_accepted():
    body = b'{"entry":[]}'
    assert whatsapp.verify_signature(body, _sign(body)) is True


def test_tampered_body_rejected():
    body = b'{"entry":[]}'
    sig = _sign(body)
    tampered = b'{"entry":[{"hacked":true}]}'
    assert whatsapp.verify_signature(tampered, sig) is False


def test_missing_header_rejected():
    assert whatsapp.verify_signature(b"{}", None) is False


def test_wrong_secret_rejected():
    body = b'{"entry":[]}'
    assert whatsapp.verify_signature(body, _sign(body, secret="wrong")) is False


def test_header_without_prefix_rejected():
    body = b'{"entry":[]}'
    raw = hmac.new(b"supersecret", body, hashlib.sha256).hexdigest()
    assert whatsapp.verify_signature(body, raw) is False
