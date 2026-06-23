from datetime import datetime, timezone

from src.modules.chat_summary import group_by_chat, format_transcript, render_briefing


# ---------------------------------------------------------------------------
# group_by_chat
# ---------------------------------------------------------------------------

def test_group_by_chat_single_chat():
    msgs = [
        {"chat_jid": "alice@s.whatsapp.net", "content": "hi"},
        {"chat_jid": "alice@s.whatsapp.net", "content": "how are you"},
    ]
    grouped = group_by_chat(msgs)
    assert list(grouped.keys()) == ["alice@s.whatsapp.net"]
    assert len(grouped["alice@s.whatsapp.net"]) == 2


def test_group_by_chat_multiple_chats():
    msgs = [
        {"chat_jid": "alice@s.whatsapp.net", "content": "hi"},
        {"chat_jid": "group@g.us", "content": "meeting at 3"},
        {"chat_jid": "alice@s.whatsapp.net", "content": "you there?"},
    ]
    grouped = group_by_chat(msgs)
    assert set(grouped.keys()) == {"alice@s.whatsapp.net", "group@g.us"}
    assert len(grouped["alice@s.whatsapp.net"]) == 2
    assert len(grouped["group@g.us"]) == 1


def test_group_by_chat_preserves_order():
    msgs = [
        {"chat_jid": "b@s.whatsapp.net", "content": "first"},
        {"chat_jid": "a@s.whatsapp.net", "content": "second"},
        {"chat_jid": "c@s.whatsapp.net", "content": "third"},
    ]
    grouped = group_by_chat(msgs)
    assert list(grouped.keys()) == ["b@s.whatsapp.net", "a@s.whatsapp.net", "c@s.whatsapp.net"]


def test_group_by_chat_empty():
    assert group_by_chat([]) == {}


# ---------------------------------------------------------------------------
# format_transcript
# ---------------------------------------------------------------------------

def _msg(content, is_from_me=0, sender="alice", sender_display=None, content_display=None, timestamp="2026-06-22 10:30:00"):
    return {
        "content": content,
        "content_display": content_display,
        "is_from_me": is_from_me,
        "sender": sender,
        "sender_display": sender_display,
        "timestamp": timestamp,
    }


def test_format_transcript_outgoing_shows_me():
    lines = format_transcript([_msg("hey", is_from_me=1)]).splitlines()
    assert lines[0].startswith("[2026-06-22 10:30] Me:")


def test_format_transcript_incoming_shows_sender():
    lines = format_transcript([_msg("hey", is_from_me=0, sender="alice")]).splitlines()
    assert lines[0].startswith("[2026-06-22 10:30] alice:")


def test_format_transcript_none_sender_falls_back_to_unknown():
    lines = format_transcript([_msg("hey", is_from_me=0, sender=None)]).splitlines()
    assert "Unknown" in lines[0]


def test_format_transcript_none_content_shows_media():
    lines = format_transcript([_msg(None)]).splitlines()
    assert "[media]" in lines[0]


def test_format_transcript_truncates_timestamp_to_minute():
    msg = _msg("hi", timestamp="2026-06-22 10:30:45")
    line = format_transcript([msg])
    assert "10:30" in line
    assert "45" not in line


def test_format_transcript_multiple_messages():
    msgs = [
        _msg("first", timestamp="2026-06-22 09:00:00"),
        _msg("second", is_from_me=1, timestamp="2026-06-22 09:01:00"),
    ]
    lines = format_transcript(msgs).splitlines()
    assert len(lines) == 2
    assert "first" in lines[0]
    assert "Me" in lines[1]


# ---------------------------------------------------------------------------
# render_briefing
# ---------------------------------------------------------------------------

FIXED_NOW = datetime(2026, 6, 22, 8, 0, 0, tzinfo=timezone.utc)  # Mon 22 Jun


def test_render_briefing_header_contains_date():
    result = render_briefing([], now=FIXED_NOW)
    assert "Mon 22 Jun" in result


def test_render_briefing_no_chats_shows_fallback():
    result = render_briefing([], now=FIXED_NOW)
    assert "No active chats" in result


def test_render_briefing_single_chat():
    summaries = [{"chat_name": "Alice", "msg_count": 5, "summary": "Asking about the event"}]
    result = render_briefing(summaries, now=FIXED_NOW)
    assert "Alice (5 msgs)" in result
    assert "Asking about the event" in result


def test_render_briefing_multiple_chats():
    summaries = [
        {"chat_name": "Alice", "msg_count": 3, "summary": "Checking in"},
        {"chat_name": "Work Group", "msg_count": 12, "summary": "Sprint discussion"},
    ]
    result = render_briefing(summaries, now=FIXED_NOW)
    assert "Alice (3 msgs)" in result
    assert "Work Group (12 msgs)" in result


def test_render_briefing_uses_utc_now_when_not_provided():
    result = render_briefing([])
    # Just verify it runs and produces a header line without crashing.
    assert "🌅 DAILY BRIEFING" in result
