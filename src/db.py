import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

# Columns selected for every message row. Kept in one place so the per-chat
# queries below stay in sync.
_MESSAGE_COLUMNS = """
    m.chat_jid        AS chat_jid,
    c.name            AS chat_name,
    m.is_from_me      AS is_from_me,
    m.sender          AS sender,
    m.sender_display  AS sender_display,
    m.content         AS content,
    m.content_display AS content_display,
    m.timestamp       AS timestamp
"""


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


def fetch_active_chats(
    lookback_hours: int,
    excluded_chats: list[str] | None = None,
) -> list[dict]:
    """Return chats with at least one message in the last `lookback_hours`.

    Each row: {chat_jid, chat_name, is_group}, most recently active first.
    Chats listed in `excluded_chats` (by JID) are omitted.
    """
    cutoff = _lookback_cutoff(lookback_hours)
    query = """
        SELECT
            m.chat_jid        AS chat_jid,
            c.name            AS chat_name,
            MAX(m.timestamp)  AS last_ts
        FROM messages m
        LEFT JOIN chats c ON c.jid = m.chat_jid
        WHERE datetime(m.timestamp) >= ?
        GROUP BY m.chat_jid
        ORDER BY last_ts DESC
    """
    with get_connection() as conn:
        rows = conn.execute(query, (cutoff,)).fetchall()
    excluded = set(excluded_chats or [])
    return [
        {
            "chat_jid": row["chat_jid"],
            "chat_name": row["chat_name"],
            "is_group": row["chat_jid"].endswith("@g.us"),
        }
        for row in rows
        if row["chat_jid"] not in excluded
    ]


def fetch_chat_messages(
    chat_jid: str,
    lookback_hours: int,
    min_messages: int = 10,
) -> list[dict]:
    """Return messages for one chat, in ascending time order.

    Fetches the greater of (all messages in the window) or (last `min_messages`):
    if the window holds fewer than `min_messages`, fall back to the most recent
    `min_messages` regardless of age. This guarantees enough context for chats
    that only had a message or two in the last day.
    """
    cutoff = _lookback_cutoff(lookback_hours)
    window_query = f"""
        SELECT {_MESSAGE_COLUMNS}
        FROM messages m
        LEFT JOIN chats c ON c.jid = m.chat_jid
        WHERE m.chat_jid = ?
          AND datetime(m.timestamp) >= ?
        ORDER BY m.timestamp ASC
    """
    floor_query = f"""
        SELECT {_MESSAGE_COLUMNS}
        FROM messages m
        LEFT JOIN chats c ON c.jid = m.chat_jid
        WHERE m.chat_jid = ?
        ORDER BY m.timestamp DESC
        LIMIT ?
    """
    with get_connection() as conn:
        rows = conn.execute(window_query, (chat_jid, cutoff)).fetchall()
        if len(rows) < min_messages:
            rows = list(reversed(conn.execute(floor_query, (chat_jid, min_messages)).fetchall()))
    return [dict(row) for row in rows]


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
