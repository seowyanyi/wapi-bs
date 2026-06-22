import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import src.db.reader
from src.db.reader import (
    _lookback_cutoff,
    fetch_individual_chats_with_last_message,
    fetch_messages_by_contact,
    fetch_messages_by_time_window,
)

SCHEMA = """
CREATE TABLE chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    last_message_time TIMESTAMP,
    ephemeral_expiration INTEGER NOT NULL DEFAULT 0,
    ephemeral_setting_timestamp INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE messages (
    id TEXT,
    chat_jid TEXT,
    sender TEXT,
    content TEXT,
    timestamp TIMESTAMP,
    is_from_me BOOLEAN,
    media_type TEXT,
    filename TEXT,
    url TEXT,
    media_key BLOB,
    file_sha256 BLOB,
    file_enc_sha256 BLOB,
    file_length INTEGER,
    deleted_at TIMESTAMP,
    quoted_message_id TEXT,
    PRIMARY KEY (id, chat_jid),
    FOREIGN KEY (chat_jid) REFERENCES chats(jid)
);
"""


def ts(hours_ago: float) -> str:
    """UTC timestamp string for N hours ago, matching SQLite datetime() format."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed(db_path: str, rows: list[dict]) -> None:
    """Insert test messages and auto-create their parent chat rows."""
    conn = sqlite3.connect(db_path)
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO chats (jid, name) VALUES (?, ?)",
            (row["chat_jid"], row.get("chat_name", row["chat_jid"])),
        )
        conn.execute(
            "INSERT INTO messages (id, chat_jid, sender, content, timestamp, is_from_me)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex.upper(),
                row["chat_jid"],
                row.get("sender", row["chat_jid"].split("@")[0]),
                row["content"],
                row["timestamp"],
                row["is_from_me"],
            ),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    monkeypatch.setattr(src.db.reader, "DB_PATH", path)
    return path


# ---------------------------------------------------------------------------
# _lookback_cutoff
# ---------------------------------------------------------------------------

def test_lookback_cutoff_is_in_the_past():
    cutoff = _lookback_cutoff(24)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert cutoff < now


def test_lookback_cutoff_has_valid_sqlite_datetime_format():
    # SQLite silently returns nothing if the format is wrong — catch it early.
    cutoff = _lookback_cutoff(1)
    datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")  # raises ValueError if format is wrong


# ---------------------------------------------------------------------------
# fetch_messages_by_time_window
# ---------------------------------------------------------------------------

def test_time_window_includes_recent_messages(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "recent", "timestamp": ts(1)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "old", "timestamp": ts(30)},
    ])
    results = fetch_messages_by_time_window(lookback_hours=24)
    contents = [r["content"] for r in results]
    assert "recent" in contents
    assert "old" not in contents


def test_time_window_includes_both_dms_and_groups(db_path):
    # Module 1 (chat summary) needs everything — no group filter here.
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "dm", "timestamp": ts(1)},
        {"chat_jid": "group@g.us", "chat_name": "Work Group", "is_from_me": 0, "content": "group", "timestamp": ts(1)},
    ])
    results = fetch_messages_by_time_window(lookback_hours=24)
    jids = {r["chat_jid"] for r in results}
    assert "alice@s.whatsapp.net" in jids
    assert "group@g.us" in jids


# ---------------------------------------------------------------------------
# fetch_messages_by_contact
# ---------------------------------------------------------------------------

def test_fetch_by_contact_scopes_to_correct_jid(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "from alice", "timestamp": ts(1)},
        {"chat_jid": "bob@s.whatsapp.net", "is_from_me": 0, "content": "from bob", "timestamp": ts(1)},
    ])
    results = fetch_messages_by_contact("alice@s.whatsapp.net", lookback_hours=24)
    assert len(results) == 1
    assert results[0]["content"] == "from alice"


def test_fetch_by_contact_respects_time_window(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "recent", "timestamp": ts(1)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "old", "timestamp": ts(30)},
    ])
    results = fetch_messages_by_contact("alice@s.whatsapp.net", lookback_hours=24)
    contents = [r["content"] for r in results]
    assert "recent" in contents
    assert "old" not in contents


# ---------------------------------------------------------------------------
# fetch_individual_chats_with_last_message
# ---------------------------------------------------------------------------

def test_individual_chats_excludes_group_chats(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "dm", "timestamp": ts(1)},
        {"chat_jid": "group@g.us", "chat_name": "Work Group", "is_from_me": 0, "content": "group msg", "timestamp": ts(1)},
    ])
    results = fetch_individual_chats_with_last_message(lookback_hours=24)
    jids = [r["chat_jid"] for r in results]
    assert "alice@s.whatsapp.net" in jids
    assert "group@g.us" not in jids


def test_individual_chats_returns_only_latest_message_per_chat(db_path):
    # Two messages from alice — only the newest should come back.
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 1, "content": "my reply", "timestamp": ts(3)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "latest from alice", "timestamp": ts(1)},
    ])
    results = fetch_individual_chats_with_last_message(lookback_hours=24)
    assert len(results) == 1
    assert results[0]["content"] == "latest from alice"
    assert results[0]["is_from_me"] == 0


def test_individual_chats_returns_one_row_per_chat(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "hi", "timestamp": ts(2)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 1, "content": "hey", "timestamp": ts(1)},
        {"chat_jid": "bob@s.whatsapp.net", "is_from_me": 0, "content": "yo", "timestamp": ts(1)},
    ])
    results = fetch_individual_chats_with_last_message(lookback_hours=24)
    jids = [r["chat_jid"] for r in results]
    assert len(jids) == 2
    assert len(set(jids)) == 2  # no duplicates
