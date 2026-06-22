# WhatsApp Chat Summary Bot

A personal AI agent that reads your WhatsApp message history, runs it through Claude, and pushes a daily chat summary to Telegram.

---

## What It Does

Every run produces a Telegram message summarising your active group and individual chats from the last 24 hours, with anything needing attention flagged.

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
         │  db/reader.py  │  — time-windowed SQLite queries
         └───────┬────────┘
                 │
                 ▼
          chat_summary
                 │
          llm/client.py  — Anthropic Claude API
                 │
                 ▼
        delivery/telegram.py  — Telegram Bot API
```

**Key design choices:**
- SQLite is queried directly; no message data leaves the machine until Claude processes it
- Delivery handles Telegram's 4096-char limit by auto-chunking long messages
- Secrets in `.env`, never hardcoded

---

## Tech Stack

- **Python 3.12**, `uv` for dependency management
- **Claude Sonnet** (Anthropic API) — LLM backbone
- **SQLite** — local WhatsApp message store via [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp)
- **Telegram Bot API** — delivery target
- **pytest** — test suite for the data layer

---

## Data Source: whatsapp-mcp

WhatsApp data is sourced from [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp) — an open-source MCP server that connects to WhatsApp Web via a local Go bridge (QR-code auth) and stores all messages in a local `messages.db` SQLite file.

No data leaves your machine until you explicitly send it to the LLM.

---

## Security

Privacy and data handling were considered at each layer of the pipeline.

**Read-only MCP**
The [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp) server was modified to remove all write operations. The pipeline can read message history but cannot send WhatsApp messages, even if the LLM were to produce unexpected output.

**Local-first data flow**
The whatsapp-mcp Go bridge binds to loopback only (`127.0.0.1`) — its REST API is not reachable from the network. `messages.db` is queried directly via SQLite on-device. Personal message data only leaves the machine at the moment it is sent to the Anthropic API, and only for that specific analysis window.

**Data minimization**
- All queries are time-windowed (`LOOKBACK_HOURS`) — not your full message history
- Nothing is persisted after a run — the Telegram message is the only output

**Secrets never committed**
`.env` and `*.db` are covered by `.gitignore`. `.env.example` ships with placeholders only.

**Locked delivery target**
Telegram output is scoped to a single `CHAT_ID` environment variable. The briefing cannot be forwarded or broadcast to other destinations.

---

## Project Status

| Layer | Status |
|---|---|
| SQLite reader (`db/reader.py`) | Done |
| Telegram delivery (`delivery/telegram.py`) | Done |
| LLM client (`llm/client.py`) | Done |
| Chat Summary module | In progress |
| Cron scheduling (n8n) | Planned |

---

## Setup

### Prerequisites

- [whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp) running locally (provides `messages.db`)
- Telegram bot token + chat ID ([BotFather](https://t.me/botfather))
- Anthropic API key

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
ANTHROPIC_API_KEY=your_api_key
LOOKBACK_HOURS=48
```

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
  db/           — SQLite reader (time-windowed queries)
  llm/          — Anthropic API client
  delivery/     — Telegram bot sender
  modules/      — Briefing modules (one file per module)
tests/
  db/           — Reader unit tests
main.py         — Entrypoint: runs all modules, pushes to Telegram
```
