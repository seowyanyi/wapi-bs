# WhatsApp Chat Summary Bot

A personal AI agent that reads your WhatsApp message history, runs it through an LLM, and pushes a daily chat summary to Telegram.

---

## What It Does

Every run produces a Telegram message summarising your active group and individual chats from the last N hours, with anything needing attention flagged.

- **Per-chat summaries** — each active chat is summarised independently in its own LLM call, then sorted by message volume.
- **Earlier vs. new split** — each transcript is divided into background context and new-since-yesterday messages, so the LLM reports only on what's new.
- **Context injection** — optional personal context and per-chat tag-based context files are fed into the prompt for sharper, more relevant summaries.
- **Chat exclusion** — chats listed in an exclusion file are skipped entirely.
- **Pluggable LLM** — runs against the Anthropic Claude API or a local Ollama model, switchable via a single env var.

---

## Architecture

```
WhatsApp ──► whatsapp-mcp (local Go bridge)
                  │
                  ▼
            messages.db  (local SQLite)
                  │
                  ▼
         ┌────────────────┐
         │   src/db.py    │  — time-windowed SQLite queries
         └───────┬────────┘
                 │
                 ▼
         src/chat_summary.py  — per-chat fetch → summarise → render
                 │
            src/llm.py        — Anthropic Claude or local Ollama
                 │
                 ▼
         src/telegram.py      — Telegram Bot API (auto-chunked)
```

**Key design choices:**
- SQLite is queried directly; no message data leaves the machine until the LLM processes it
- Delivery handles Telegram's 4096-char limit by auto-chunking long messages
- LLM output is sanitised for Telegram's Markdown parser before sending
- Secrets in `.env`, never hardcoded

---

## Tech Stack

- **Python 3.12**, `uv` for dependency management
- **Anthropic Claude API** or **local Ollama** — pluggable LLM backbone (`LLM_PROVIDER`)
- **SQLite** — local WhatsApp message store via [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp)
- **Telegram Bot API** — delivery target
- **pytest** — test suite for the data and rendering layers

---

## Data Source: whatsapp-mcp

WhatsApp data is sourced from [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp) — an open-source MCP server that connects to WhatsApp Web via a local Go bridge (QR-code auth) and stores all messages in a local `messages.db` SQLite file.

No data leaves your machine until you explicitly send it to the LLM. With `LLM_PROVIDER=local` (Ollama), nothing leaves the machine at all.

---

## Security

Privacy and data handling were considered at each layer of the pipeline.

**Read-only MCP**
The [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp) server was modified to remove all write operations. The pipeline can read message history but cannot send WhatsApp messages, even if the LLM were to produce unexpected output.

**Local-first data flow**
The whatsapp-mcp Go bridge binds to loopback only (`127.0.0.1`) — its REST API is not reachable from the network. `messages.db` is queried directly via SQLite on-device. With the Anthropic provider, personal message data only leaves the machine at the moment it is sent to the API, and only for that specific analysis window. With the local Ollama provider, it never leaves the machine.

**Data minimization**
- All queries are time-windowed (`LOOKBACK_HOURS`) — not your full message history
- Nothing is persisted after a run — the Telegram message is the only output

**Secrets never committed**
`.env` and `*.db` are covered by `.gitignore`. `.env.example` ships with placeholders only.

**Locked delivery target**
Telegram output is scoped to a single `TELEGRAM_CHAT_ID` environment variable. The briefing cannot be forwarded or broadcast to other destinations.

---

## Setup

### Prerequisites

- [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp) running locally (provides `messages.db`)
- Telegram bot token + chat ID ([BotFather](https://t.me/botfather))
- An Anthropic API key, **or** [Ollama](https://ollama.com) running locally

### Install

```bash
git clone https://github.com/seowyanyi/WAPI-BS
cd WAPI-BS
uv sync
```

### Configure

```bash
cp .env.example .env
# Fill in the values
```

```env
DB_PATH=/path/to/messages.db
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
LOOKBACK_HOURS=48
EXCLUDED_CHATS_PATH=excluded_chats.txt

# LLM provider: "anthropic" (default) or "local" (Ollama)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key
ANTHROPIC_MODEL=claude-sonnet-4-6
# Used only when LLM_PROVIDER=local
OLLAMA_MODEL=llama3.1
```

### Optional context

- `context/personal.md` — background about you, injected into every summary prompt
- `context/chats.toml` — maps chat JIDs to reusable context tags (see `context/chats.toml.example`)
- `excluded_chats.txt` — chat JIDs to skip, one per line (`#` comments allowed)

### Run

```bash
uv run python main.py
```

### Tests

```bash
uv run pytest
```

---

## Repository Structure

```
src/
  db.py              — SQLite reader (time-windowed queries + last-N floor)
  llm.py             — LLM client (Anthropic or Ollama)
  telegram.py        — Telegram bot sender (auto-chunking)
  context_loader.py  — personal + per-chat context loading
  chat_summary.py    — fetch → summarise → render briefing
tests/
  test_db.py             — reader unit tests
  test_chat_summary.py   — transcript + briefing rendering tests
main.py                  — Entrypoint: builds the briefing, pushes to Telegram
```
