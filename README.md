# whatsapp-llm-bot

WhatsApp customer support bot for a fictional bookstore, powered by Claude with tool use. Built on FastAPI and the Meta WhatsApp Cloud API.

The bot answers customer questions in natural language: searches the catalog, looks up book details, and suggests similar titles. Claude decides when to call each tool based on the conversation — no rigid intent-classification, no scripted flows.

```
        ┌────────────┐    webhook     ┌─────────────┐
        │ WhatsApp   │ ─────────────▶ │  FastAPI    │
        │ Cloud API  │ ◀───────────── │  /webhook   │
        └────────────┘   send_message └──────┬──────┘
                                             │
                                             ▼
                                      ┌─────────────┐
                                      │   Claude    │
                                      │  (Opus 4.7) │
                                      └──────┬──────┘
                                             │ tool_use
                                             ▼
                                  search_catalog · get_book_details
                                       · suggest_similar
```

## Tech stack

- **Backend**: Python 3.11 · FastAPI · Pydantic
- **LLM**: Anthropic Claude Opus 4.7 (`claude-opus-4-7`)
- **Messaging**: Meta WhatsApp Cloud API
- **Patterns**: Tool use with the SDK's beta tool runner · prompt caching · adaptive thinking

## What this repo demonstrates

This is a clean, modern reference for building an LLM-powered WhatsApp bot. Specifically:

1. **Tool use with the Anthropic SDK's beta tool runner.** Tools are declared as typed Python functions (`@beta_tool`) — the SDK auto-generates JSON schemas from signatures + docstrings, drives the agentic loop, and stops when Claude has nothing more to call. See [`app/tools.py`](app/tools.py) and [`app/agent.py`](app/agent.py).
2. **Prompt caching on the system prompt.** The system prompt (role, tone, catalog summary) is large and stable; it's cached with `cache_control: ephemeral`, so repeat conversations from any user only pay full input price on the first request. Verified via `usage.cache_read_input_tokens`.
3. **Adaptive thinking.** The agent uses `thinking: {type: "adaptive"}` with `effort: "medium"` — Claude decides per-message how much to think. No hardcoded token budget.
4. **WhatsApp webhook security.** Webhook verification (`hub.challenge`) and HMAC-SHA256 signature validation of incoming payloads (`X-Hub-Signature-256`). See [`app/whatsapp.py`](app/whatsapp.py).
5. **Stateless HTTP, stateful conversation.** Per-user conversation history kept in an in-memory store keyed by phone number. The store is swappable — replace with Redis for production (see "Production considerations" below).

## Features

- Natural-language Q&A about a catalog of books (genre, author, price, stock).
- Three tools the model can call:
  - `search_catalog(query, max_results)` — full-text search across title, author, genre.
  - `get_book_details(book_id)` — full record for one book (price, stock, summary).
  - `suggest_similar(book_id, max_results)` — recommend titles by shared genre.
- Per-user conversation memory (in-process; swappable).
- Webhook signature verification.
- Type-safe end to end (Pydantic + type hints).

## Quick start

```bash
git clone https://github.com/DavoLobos/whatsapp-llm-bot.git
cd whatsapp-llm-bot

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in ANTHROPIC_API_KEY, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID,
# WHATSAPP_VERIFY_TOKEN, WHATSAPP_APP_SECRET

uvicorn app.main:app --reload --port 8000
```

To receive WhatsApp messages locally, expose port 8000 with [ngrok](https://ngrok.com):

```bash
ngrok http 8000
```

Configure the WhatsApp Business webhook in Meta Developer Console:
- Callback URL: `https://<your-ngrok-domain>/webhook`
- Verify token: the value of `WHATSAPP_VERIFY_TOKEN` in `.env`
- Subscribe to: `messages`

Send a WhatsApp message to the business number — the bot replies.

## Configuration

All settings come from environment variables (loaded via `pydantic-settings` from `.env`).

| Variable                    | Purpose                                                      |
|-----------------------------|--------------------------------------------------------------|
| `ANTHROPIC_API_KEY`         | Anthropic API key for Claude                                 |
| `WHATSAPP_TOKEN`            | Meta Cloud API access token (system user, long-lived)        |
| `WHATSAPP_PHONE_NUMBER_ID`  | Phone Number ID from Meta Business Manager                   |
| `WHATSAPP_VERIFY_TOKEN`     | Shared secret used during webhook verification (you pick it) |
| `WHATSAPP_APP_SECRET`       | App secret from Meta — used to verify webhook signatures     |
| `MODEL_ID`                  | Claude model ID. Default: `claude-opus-4-7`                  |
| `MAX_HISTORY_MESSAGES`      | Conversation turns to keep per user. Default: `20`           |

## Project layout

```
app/
├── main.py        FastAPI app, webhook routes
├── config.py      Pydantic settings, loaded from .env
├── agent.py       Claude integration, tool runner loop, caching
├── tools.py       Tool functions: search/details/suggest
├── catalog.py     In-memory catalog with sample data
├── whatsapp.py    WhatsApp Cloud API client (send + verify signature)
├── session.py     Per-user conversation history (in-memory)
└── data/
    └── books.json Sample bookstore catalog
tests/
├── test_catalog.py
└── test_whatsapp_signature.py
```

## How tool use works here

The flow on each user message:

1. Webhook receives a `text` message from WhatsApp Cloud API. Signature is verified before parsing.
2. The user's phone number is the conversation key; we load their history (last N turns).
3. The new user message is appended and the SDK's `client.beta.messages.tool_runner(...)` is invoked with our three tools.
4. Internally the runner calls the API, executes tools when Claude requests them, feeds results back, and loops until Claude has a final text response.
5. The final reply is sent back to the user via the WhatsApp Cloud API.

Tools are declared as plain typed Python functions with the `@beta_tool` decorator:

```python
@beta_tool
def search_catalog(query: str, max_results: int = 5) -> list[dict]:
    """Search the bookstore catalog by title, author, or genre.

    Args:
        query: Free-text query.
        max_results: Maximum number of results.
    """
    return catalog.search(query, limit=max_results)
```

No hand-written JSON schemas — the SDK derives them from the signature and docstring.

## How prompt caching works here

The system prompt is built once and contains:

- The bot's role and tone instructions.
- A high-level catalog summary (genres available, top picks).
- Behavioral guidance (always quote prices, ask before searching for ambiguous queries, etc.).

It is wrapped in a `cache_control: {type: "ephemeral"}` block. On the first request the system prompt is written to the cache (~1.25x input cost). Every subsequent request — from any user — reads it back at ~10% of input cost. Conversation messages live after the cache breakpoint, so user-specific content never invalidates the shared prefix.

You can verify cache hits in the logs: each API response includes `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens`.

## Production considerations

This repo is a clean reference, not a turnkey deploy. To run it for real, swap out:

- **Session store.** `app/session.py` uses an in-process dict. Replace with Redis (or any KV store) for horizontal scaling and persistence.
- **Catalog source.** `app/catalog.py` loads from a JSON file at boot. Replace with your database or product API.
- **Conversation pruning.** History is truncated to `MAX_HISTORY_MESSAGES` per user. For longer conversations consider Claude's [server-side compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) (beta, `compact-2026-01-12`).
- **Idempotency.** WhatsApp may retry webhook deliveries. Track processed message IDs to avoid double-replying.
- **Rate limiting.** Add per-user rate limits to defend against abuse and to control LLM cost.
- **Observability.** Wire logs into structured logging + a metrics pipeline; track `usage` totals per conversation.

## Disclaimer

The bookstore "La Librería" and its catalog are entirely fictional. This repository is a portfolio reference — not affiliated with any real business or company.

## License

MIT
