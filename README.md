# whatsapp-llm-bot

**Live demo:** [libreriademo.duckdns.org](https://libreriademo.duckdns.org)

WhatsApp customer support bot for a fictional bookstore, powered by Claude with tool use. Built on FastAPI and the Meta WhatsApp Cloud API.

The bot answers customer questions in natural language: searches the catalog, looks up book details, and suggests similar titles. Claude decides when to call each tool based on the conversation — no rigid intent-classification, no scripted flows.

The same FastAPI app also serves a **web chat demo** at `/`, so the bot can be tried in a browser without any WhatsApp setup. The [live demo](https://libreriademo.duckdns.org) runs against a Claude Pro/Max subscription via the Claude Agent SDK — no API key billing.

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

## Guardrails — what the bot will *not* do

Tool use gives a model capabilities; it doesn't give it judgment. By default, asking the bot *"what books do you have?"* would dump the entire catalog — title, author, price, and stock count for every product. For a real business that's an information leak: a competitor can scrape your prices, your inventory, and your full assortment in two messages.

The system prompt (in [`app/mcp_tools.py`](app/mcp_tools.py) and [`app/agent.py`](app/agent.py)) declares an explicit policy on top of the model's capabilities:

- The bot will **not** list the full catalog, even when asked directly.
- For open-ended questions like *"what do you have?"*, it answers with the **genres** available and asks the customer to narrow down.
- It caps any single response to a small number of titles.
- It doesn't reveal exact stock counts unless asked about a specific title.

**Verify it on the [live demo](https://libreriademo.duckdns.org):**

```
You: ¿qué libros tenés en stock?
Bot: No compartimos el catálogo completo, pero manejamos: Realismo mágico,
     Cuento, Novela experimental, Ensayo, Distopía, Fantasía, Thriller.
     ¿Hay un género o autor que te interese?

You: ¿tenés algo de Borges?
Bot: Tenemos dos títulos de Borges: Ficciones ($6.900) y El Aleph ($7.100).
     ¿Te interesa alguno en particular?
```

This is a policy you tune per business, not per model — and that's exactly why it lives in the system prompt rather than in code. Shipping a new policy is a three-line edit; the code surface and the tool definitions don't change.

## Features

- Natural-language Q&A about a catalog of books (genre, author, price, stock).
- Three tools the model can call:
  - `search_catalog(query, max_results)` — full-text search across title, author, genre.
  - `get_book_details(book_id)` — full record for one book (price, stock, summary).
  - `suggest_similar(book_id, max_results)` — recommend titles by shared genre.
- Per-user conversation memory (in-process; swappable).
- Webhook signature verification.
- Type-safe end to end (Pydantic + type hints).

## Web demo

The app serves a minimal single-page chat UI at `GET /` that calls `POST /chat`. The chat endpoint uses the `app/agent_claude_code.py` path (Claude Agent SDK + Claude Code auth), so the demo can run on a server that's logged into a Claude Pro/Max subscription without any Anthropic API key. Per-session and global daily caps live in `app/rate_limit.py`.

```bash
# requires `claude` (Claude Code CLI) installed and logged in
uvicorn app.main:app --port 8000
# open http://localhost:8000
```

## Try it without setting up WhatsApp

Two CLI entry points let you chat with the bot logic (system prompt + tools) without provisioning a Meta WhatsApp number.

| Script | Auth | When to use |
|---|---|---|
| `scripts/chat.py` | `ANTHROPIC_API_KEY` env var | Standard path. Uses the Anthropic API directly — same code path as production. |
| `scripts/chat_max.py` | Claude Code (`claude` CLI) auth | If you have a Claude Pro/Max subscription, run the bot through the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) and consume from your subscription instead of metered API billing. |

```bash
# Option A — Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/chat.py                              # interactive
python scripts/chat.py "¿qué libros de Borges tenés?"  # one-shot

# Option B — Claude Pro/Max subscription (requires `claude` CLI installed and logged in)
python scripts/chat_max.py                          # interactive
python scripts/chat_max.py "¿qué libros de Borges tenés?"
```

Both scripts exercise the same logic (system prompt, three tools, conversation state). The production code path in `app/agent.py` always uses the Anthropic SDK directly — `chat_max.py` is a deliberate parallel implementation showing how to wire the same bot through the Agent SDK for local testing.

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
