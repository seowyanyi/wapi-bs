from datetime import datetime, timezone

from src.modules.chat_summary import format_transcript, render_briefing


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


def test_format_transcript_with_cutoff_splits_sections():
    cutoff = "2026-06-22 10:00:00"
    msgs = [
        _msg("old message", timestamp="2026-06-22 09:00:00"),
        _msg("new message", timestamp="2026-06-22 11:00:00"),
    ]
    result = format_transcript(msgs, cutoff=cutoff)
    assert "EARLIER CONTEXT" in result
    assert "NEW SINCE YESTERDAY" in result
    ctx_pos = result.index("EARLIER CONTEXT")
    new_pos = result.index("NEW SINCE YESTERDAY")
    old_pos = result.index("old message")
    new_msg_pos = result.index("new message")
    assert ctx_pos < old_pos < new_pos < new_msg_pos


def test_format_transcript_with_cutoff_no_context():
    cutoff = "2026-06-22 08:00:00"
    msgs = [_msg("new message", timestamp="2026-06-22 11:00:00")]
    result = format_transcript(msgs, cutoff=cutoff)
    assert "EARLIER CONTEXT" not in result
    assert "NEW SINCE YESTERDAY" in result
    assert "new message" in result


def test_format_transcript_with_cutoff_no_new_messages():
    cutoff = "2026-06-22 12:00:00"
    msgs = [_msg("old message", timestamp="2026-06-22 09:00:00")]
    result = format_transcript(msgs, cutoff=cutoff)
    assert "EARLIER CONTEXT" in result
    assert "no new messages" in result


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
