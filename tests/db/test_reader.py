import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.db.reader import (
    _lookback_cutoff,
    fetch_active_chats,
    fetch_chat_messages,
    load_excluded_chats,
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
    sender_display TEXT,
    content TEXT,
    content_display TEXT,
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
            "INSERT INTO messages (id, chat_jid, sender, sender_display, content, content_display, timestamp, is_from_me)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex.upper(),
                row["chat_jid"],
                row.get("sender", row["chat_jid"].split("@")[0]),
                row.get("sender_display"),
                row["content"],
                row.get("content_display"),
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
    monkeypatch.setenv("DB_PATH", path)
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
# fetch_active_chats
# ---------------------------------------------------------------------------

def test_active_chats_includes_chats_with_recent_messages(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "recent", "timestamp": ts(1)},
        {"chat_jid": "stale@s.whatsapp.net", "is_from_me": 0, "content": "old", "timestamp": ts(30)},
    ])
    jids = {c["chat_jid"] for c in fetch_active_chats(lookback_hours=24)}
    assert "alice@s.whatsapp.net" in jids
    assert "stale@s.whatsapp.net" not in jids


def test_active_chats_returns_one_row_per_chat(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "hi", "timestamp": ts(2)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 1, "content": "hey", "timestamp": ts(1)},
        {"chat_jid": "bob@s.whatsapp.net", "is_from_me": 0, "content": "yo", "timestamp": ts(1)},
    ])
    chats = fetch_active_chats(lookback_hours=24)
    jids = [c["chat_jid"] for c in chats]
    assert len(jids) == 2
    assert len(set(jids)) == 2


def test_active_chats_flags_groups(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "dm", "timestamp": ts(1)},
        {"chat_jid": "group@g.us", "chat_name": "Work Group", "is_from_me": 0, "content": "group", "timestamp": ts(1)},
    ])
    by_jid = {c["chat_jid"]: c for c in fetch_active_chats(lookback_hours=24)}
    assert by_jid["group@g.us"]["is_group"] is True
    assert by_jid["alice@s.whatsapp.net"]["is_group"] is False


def test_active_chats_orders_most_recent_first(db_path):
    seed(db_path, [
        {"chat_jid": "older@s.whatsapp.net", "is_from_me": 0, "content": "older", "timestamp": ts(5)},
        {"chat_jid": "newer@s.whatsapp.net", "is_from_me": 0, "content": "newer", "timestamp": ts(1)},
    ])
    jids = [c["chat_jid"] for c in fetch_active_chats(lookback_hours=24)]
    assert jids == ["newer@s.whatsapp.net", "older@s.whatsapp.net"]


def test_active_chats_excludes_listed_jids(db_path):
    seed(db_path, [
        {"chat_jid": "alpha@g.us", "chat_name": "Alpha", "is_from_me": 0, "content": "msg", "timestamp": ts(1)},
        {"chat_jid": "beta@g.us", "chat_name": "Beta", "is_from_me": 0, "content": "msg", "timestamp": ts(1)},
    ])
    jids = {c["chat_jid"] for c in fetch_active_chats(lookback_hours=24, excluded_chats=["alpha@g.us"])}
    assert "alpha@g.us" not in jids
    assert "beta@g.us" in jids


# ---------------------------------------------------------------------------
# fetch_chat_messages — window + last-N floor
# ---------------------------------------------------------------------------

def test_chat_messages_returns_window_when_above_floor(db_path):
    # 12 recent messages, floor is 10 → return all 12 from the window.
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": f"m{i}", "timestamp": ts(1)}
        for i in range(12)
    ])
    msgs = fetch_chat_messages("alice@s.whatsapp.net", lookback_hours=24, min_messages=10)
    assert len(msgs) == 12


def test_chat_messages_falls_back_to_last_n_when_window_is_thin(db_path):
    # Only 2 messages in the window, but 15 older ones exist → return last 10.
    rows = [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": f"old{i}", "timestamp": ts(30 + i)}
        for i in range(15)
    ] + [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "recent1", "timestamp": ts(2)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "recent2", "timestamp": ts(1)},
    ]
    seed(db_path, rows)
    msgs = fetch_chat_messages("alice@s.whatsapp.net", lookback_hours=24, min_messages=10)
    assert len(msgs) == 10
    # Most recent message is last (ascending order).
    assert msgs[-1]["content"] == "recent2"


def test_chat_messages_returns_ascending_by_time(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "first", "timestamp": ts(3)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 1, "content": "second", "timestamp": ts(2)},
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "third", "timestamp": ts(1)},
    ])
    msgs = fetch_chat_messages("alice@s.whatsapp.net", lookback_hours=24, min_messages=10)
    assert [m["content"] for m in msgs] == ["first", "second", "third"]


def test_chat_messages_scopes_to_one_chat(db_path):
    seed(db_path, [
        {"chat_jid": "alice@s.whatsapp.net", "is_from_me": 0, "content": "from alice", "timestamp": ts(1)},
        {"chat_jid": "bob@s.whatsapp.net", "is_from_me": 0, "content": "from bob", "timestamp": ts(1)},
    ])
    msgs = fetch_chat_messages("alice@s.whatsapp.net", lookback_hours=24)
    assert {m["content"] for m in msgs} == {"from alice"}


# ---------------------------------------------------------------------------
# load_excluded_chats
# ---------------------------------------------------------------------------

def test_load_excluded_chats_returns_empty_with_no_config(monkeypatch):
    monkeypatch.delenv("EXCLUDED_CHATS_PATH", raising=False)
    assert load_excluded_chats() == []


def test_load_excluded_chats_returns_empty_when_file_missing(monkeypatch):
    monkeypatch.setenv("EXCLUDED_CHATS_PATH", "/nonexistent/excluded_chats.txt")
    assert load_excluded_chats() == []


def test_load_excluded_chats_parses_jids(tmp_path):
    f = tmp_path / "excluded.txt"
    f.write_text("111111111111111111@g.us\n222222222222222222@g.us\n")
    result = load_excluded_chats(str(f))
    assert result == ["111111111111111111@g.us", "222222222222222222@g.us"]


def test_load_excluded_chats_skips_comments_and_blank_lines(tmp_path):
    f = tmp_path / "excluded.txt"
    f.write_text("# this is a comment\n\n111111111111111111@g.us\n\n# another comment\n")
    result = load_excluded_chats(str(f))
    assert result == ["111111111111111111@g.us"]


def test_load_excluded_chats_reads_from_env_var(tmp_path, monkeypatch):
    f = tmp_path / "excluded.txt"
    f.write_text("111111111111111111@g.us\n")
    monkeypatch.setenv("EXCLUDED_CHATS_PATH", str(f))
    assert load_excluded_chats() == ["111111111111111111@g.us"]


def test_load_excluded_chats_path_arg_overrides_env_var(tmp_path, monkeypatch):
    env_file = tmp_path / "from_env.txt"
    env_file.write_text("333333333333333333@g.us\n")
    arg_file = tmp_path / "from_arg.txt"
    arg_file.write_text("111111111111111111@g.us\n")
    monkeypatch.setenv("EXCLUDED_CHATS_PATH", str(env_file))
    assert load_excluded_chats(str(arg_file)) == ["111111111111111111@g.us"]
