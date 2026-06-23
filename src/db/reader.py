import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

def load_excluded_chats(path: str | None = None) -> list[str]:
    """Load chat JIDs to exclude, one per line, from a text file.

    Reads from `path` if given, otherwise falls back to EXCLUDED_CHATS_PATH env var.
    Returns an empty list if the file is missing or the path is unset.
    """
    resolved = path or os.getenv("EXCLUDED_CHATS_PATH", "")
    if not resolved:
        return []
    try:
        with open(resolved) as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        return []


def fetch_messages_by_time_window(
    lookback_hours: int,
    excluded_chats: list[str] | None = None,
) -> list[dict]:
    """Return all messages within the last `lookback_hours`.

    Each row is a dict with: chat_jid, chat_name, sender, content, timestamp, is_from_me.
    Chats listed in `excluded_chats` (by JID) are omitted.
    """
    cutoff = _lookback_cutoff(lookback_hours)
    query = """
        SELECT
            m.chat_jid        AS chat_jid,
            c.name            AS chat_name,
            m.is_from_me      AS is_from_me,
            m.sender          AS sender,
            m.sender_display  AS sender_display,
            m.content         AS content,
            m.content_display AS content_display,
            m.timestamp       AS timestamp
        FROM messages m
        LEFT JOIN chats c ON c.jid = m.chat_jid
        WHERE datetime(m.timestamp) >= ?
        ORDER BY m.timestamp ASC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    messages = [dict(row) for row in rows]
    if excluded_chats:
        messages = [m for m in messages if m["chat_jid"] not in excluded_chats]
    return messages


def fetch_messages_by_contact(
    contact_jid: str,
    lookback_hours: int,
) -> list[dict]:
    """Return messages for a specific contact within the last `lookback_hours`.

    `contact_jid` is the WhatsApp JID, e.g. '6512345678@s.whatsapp.net'.
    """
    cutoff = _lookback_cutoff(lookback_hours)
    query = """
        SELECT
            m.chat_jid        AS chat_jid,
            c.name            AS chat_name,
            m.is_from_me      AS is_from_me,
            m.sender          AS sender,
            m.sender_display  AS sender_display,
            m.content         AS content,
            m.content_display AS content_display,
            m.timestamp       AS timestamp
        FROM messages m
        LEFT JOIN chats c ON c.jid = m.chat_jid
        WHERE m.chat_jid = ?
          AND datetime(m.timestamp) >= ?
        ORDER BY m.timestamp ASC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (contact_jid, cutoff)).fetchall()
    return [dict(row) for row in rows]


def fetch_individual_chats_with_last_message(
    lookback_hours: int,
    excluded_chats: list[str] | None = None,
) -> list[dict]:
    """Return one row per individual (non-group) chat, showing only the latest message.

    Filters to chats that had activity within `lookback_hours`.
    """
    cutoff = _lookback_cutoff(lookback_hours)
    query = """
        SELECT
            m.chat_jid        AS chat_jid,
            c.name            AS chat_name,
            m.is_from_me      AS is_from_me,
            m.sender          AS sender,
            m.sender_display  AS sender_display,
            m.content         AS content,
            m.content_display AS content_display,
            m.timestamp       AS timestamp
        FROM messages m
        LEFT JOIN chats c ON c.jid = m.chat_jid
        INNER JOIN (
            SELECT chat_jid, MAX(timestamp) AS max_ts
            FROM messages
            WHERE datetime(timestamp) >= ?
              AND chat_jid NOT LIKE '%@g.us'
            GROUP BY chat_jid
        ) latest
          ON m.chat_jid = latest.chat_jid
         AND m.timestamp = latest.max_ts
        ORDER BY m.timestamp DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    chats = [dict(row) for row in rows]
    if excluded_chats:
        chats = [c for c in chats if c["chat_jid"] not in excluded_chats]
    return chats

@contextmanager
def get_connection(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or os.getenv("DB_PATH", ""))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _lookback_cutoff(hours: int) -> str:
    """Return an ISO 8601 UTC string for `hours` ago, for use with datetime() in SQLite."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")
