# WhatsApp Intelligence Briefing

A personal AI briefing agent that reads your WhatsApp message history, runs it through Claude, and pushes a structured daily digest to Telegram.

---

## What It Does

Every run produces a Telegram briefing with three sections:

| Module | What it does |
|---|---|
| **Chat Summary** | Summarises active group and individual chats from the last 24–48 hours. Flags anything needing attention. |
| **Unreplied Messages** | Finds individual chats where the last message is inbound and unanswered. LLM classifies urgency: high / medium / low. |
| **Priority Contact Monitoring** | Monitors a user-defined contact list against stated priorities. Assesses sentiment trend and recommends action. Config-driven via a plain text file. |

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
    ┌────────────┼────────────┐
    ▼            ▼            ▼
chat_summary  unreplied  priority_contact
    │            │            │
    └────────────┴────────────┘
                 │
          llm/client.py  — Anthropic Claude API
                 │
                 ▼
        delivery/telegram.py  — Telegram Bot API
```

**Key design choices:**
- Each briefing module is fully independent — runs and fails in isolation
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
Each module sends the bare minimum to the LLM:
- All queries are time-windowed (`LOOKBACK_HOURS`) — not your full message history
- Unreplied Messages only pulls the *last message per chat*, not full threads
- Priority Contact Monitoring only fetches messages from the contacts explicitly listed in your config
- Nothing is persisted after a run — the Telegram briefing is the only output

**Secrets never committed**
`.env`, `*.db`, and `priority_contacts.txt` are all covered by `.gitignore`. `.env.example` ships with placeholders only.

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
| Unreplied Messages module | In progress |
| Priority Contact Monitoring module | In progress |
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
PRIORITY_CONFIG_PATH=priority_contacts.txt
```

### Priority Contacts

Create `priority_contacts.txt` — one entry per line:

```
6512345678@s.whatsapp.net | Follow up on project proposal
6598765432@s.whatsapp.net | Monitor sentiment re: contract renewal
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
