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


# ---------------------------------------------------------------------------
# fetch_messages_by_time_window — exclusion filtering
# ---------------------------------------------------------------------------

def test_time_window_excluded_chat_messages_are_removed(db_path):
    seed(db_path, [
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 1, "sender": "6590000001", "content": "draft ready for review", "timestamp": ts(1)},
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 0, "sender": "6590000002", "content": "looks good", "timestamp": ts(1)},
        {"chat_jid": "222222222222222222@g.us", "chat_name": "Weekly Standup",
         "is_from_me": 1, "sender": "6590000001", "content": "meeting at 10am", "timestamp": ts(1)},
    ])
    results = fetch_messages_by_time_window(lookback_hours=24, excluded_chats=["111111111111111111@g.us"])
    jids = {r["chat_jid"] for r in results}
    assert "111111111111111111@g.us" not in jids
    assert "222222222222222222@g.us" in jids


def test_time_window_all_messages_from_excluded_chat_are_removed(db_path):
    # Excluded chat has multiple messages — every one should be gone
    seed(db_path, [
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 1, "sender": "6590000001", "content": "first message", "timestamp": ts(3)},
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 0, "sender": "6590000002", "content": "second message", "timestamp": ts(2)},
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 1, "sender": "6590000001", "content": "third message", "timestamp": ts(1)},
    ])
    results = fetch_messages_by_time_window(lookback_hours=24, excluded_chats=["111111111111111111@g.us"])
    assert results == []


def test_time_window_multiple_chats_excluded(db_path):
    seed(db_path, [
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 1, "sender": "6590000001", "content": "msg1", "timestamp": ts(1)},
        {"chat_jid": "222222222222222222@g.us", "chat_name": "Weekly Standup",
         "is_from_me": 0, "sender": "6590000002", "content": "msg2", "timestamp": ts(1)},
        {"chat_jid": "6590000003@s.whatsapp.net", "chat_name": "Carol",
         "is_from_me": 0, "sender": "6590000003", "content": "msg3", "timestamp": ts(1)},
    ])
    excluded = ["111111111111111111@g.us", "222222222222222222@g.us"]
    results = fetch_messages_by_time_window(lookback_hours=24, excluded_chats=excluded)
    jids = {r["chat_jid"] for r in results}
    assert "111111111111111111@g.us" not in jids
    assert "222222222222222222@g.us" not in jids
    assert "6590000003@s.whatsapp.net" in jids


def test_time_window_empty_exclusion_list_returns_all(db_path):
    seed(db_path, [
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 1, "sender": "6590000001", "content": "msg", "timestamp": ts(1)},
    ])
    results = fetch_messages_by_time_window(lookback_hours=24, excluded_chats=[])
    assert len(results) == 1


def test_time_window_exclusion_not_present_has_no_effect(db_path):
    seed(db_path, [
        {"chat_jid": "111111111111111111@g.us", "chat_name": "Project Alpha",
         "is_from_me": 1, "sender": "6590000001", "content": "msg", "timestamp": ts(1)},
    ])
    results = fetch_messages_by_time_window(lookback_hours=24, excluded_chats=["999999999999999999@g.us"])
    assert len(results) == 1


# ---------------------------------------------------------------------------
# fetch_individual_chats_with_last_message — exclusion filtering
# ---------------------------------------------------------------------------

def test_individual_chats_excluded_dm_is_filtered_out(db_path):
    seed(db_path, [
        {"chat_jid": "6590000001@s.whatsapp.net", "chat_name": "Carol",
         "is_from_me": 0, "sender": "6590000001", "content": "are you free tomorrow?", "timestamp": ts(1)},
        {"chat_jid": "6590000002@s.whatsapp.net", "chat_name": "Dave",
         "is_from_me": 0, "sender": "6590000002", "content": "sounds good", "timestamp": ts(1)},
    ])
    results = fetch_individual_chats_with_last_message(lookback_hours=24, excluded_chats=["6590000001@s.whatsapp.net"])
    jids = {r["chat_jid"] for r in results}
    assert "6590000001@s.whatsapp.net" not in jids
    assert "6590000002@s.whatsapp.net" in jids


def test_individual_chats_no_exclusions_returns_all_dms(db_path):
    seed(db_path, [
        {"chat_jid": "6590000001@s.whatsapp.net", "chat_name": "Carol",
         "is_from_me": 0, "sender": "6590000001", "content": "are you free tomorrow?", "timestamp": ts(1)},
        {"chat_jid": "6590000002@s.whatsapp.net", "chat_name": "Dave",
         "is_from_me": 0, "sender": "6590000002", "content": "sounds good", "timestamp": ts(1)},
    ])
    results = fetch_individual_chats_with_last_message(lookback_hours=24)
    jids = {r["chat_jid"] for r in results}
    assert "6590000001@s.whatsapp.net" in jids
    assert "6590000002@s.whatsapp.net" in jids
