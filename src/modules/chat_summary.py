"""
Chat summary module.

Per active chat: fetch messages (floor of last 10) → one LLM call → summary.
Routing into sections + the final briefing layout come in later steps; for now
we render a flat list so the pipeline stays runnable.
"""

from datetime import datetime, timezone

from src.llm.client import call_model
from src.db.reader import (
    fetch_active_chats,
    fetch_chat_messages,
    load_excluded_chats,
)


def run(lookback_hours: int = 24) -> str:
    """Fetch active chats, summarise each via LLM, and return a formatted briefing."""
    excluded_chats = load_excluded_chats()
    chats = fetch_active_chats(lookback_hours, excluded_chats)

    print(f"\nFound {len(chats)} active chats in the last {lookback_hours}h\n")

    summaries = []
    for chat in chats:
        chat_name = chat["chat_name"] or chat["chat_jid"]
        messages = fetch_chat_messages(chat["chat_jid"], lookback_hours)
        print(f"--- {chat_name} [{chat['chat_jid']}] ({len(messages)} msgs) ---")
        transcript = format_transcript(messages)
        print(transcript)
        print(f"\n→ Sending to LLM...")
        summary = _summarise_chat(chat_name, transcript)
        print(f"← Summary: {summary}\n")
        summaries.append({
            "chat_jid": chat["chat_jid"],
            "chat_name": chat_name,
            "is_group": chat["is_group"],
            "msg_count": len(messages),
            "summary": summary,
        })

    summaries.sort(key=lambda x: x["msg_count"], reverse=True)
    return render_briefing(summaries)


def format_transcript(messages: list[dict]) -> str:
    """Format a list of messages as a readable transcript for the LLM."""
    lines = []
    for m in messages:
        sender = "Me" if m["is_from_me"] else (m["sender_display"] or m["sender"] or "Unknown")
        ts = m["timestamp"][:16]  # "YYYY-MM-DD HH:MM"
        content = m["content_display"] or m["content"] or "[media]"
        lines.append(f"[{ts}] {sender}: {content}")
    return "\n".join(lines)


def _summarise_chat(chat_name: str, transcript: str) -> str:
    """Summarise one chat via the LLM, returning a free-form summary string."""
    system = (
        "You are Yan Yi's personal daily WhatsApp intelligence briefing assistant. "
        "You will be given the recent message transcript of a single chat. Produce a "
        "concise summary (no more than 3 sentences) of the key points, decisions, and "
        "action items. Write in a clear, professional tone. Do not include a title or "
        "the chat name — go straight into the content."
    )
    user_prompt = f"Transcript of the chat named '{chat_name}':\n\n{transcript}\n"
    return call_model(user_prompt, system=system).strip()


def _clean_summary(text: str) -> str:
    """Sanitize LLM output for Telegram Markdown rendering.

    - Converts **bold** → *bold* (Telegram Markdown uses single asterisks).
    """
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    return text


def render_briefing(summaries: list[dict], now: datetime | None = None) -> str:
    """Render a flat briefing string.

    Each entry must have: chat_name (str), msg_count (int), summary (str).
    Section routing replaces this flat layout in a later step.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    date_str = f"{now.strftime('%a')} {now.day} {now.strftime('%b')}"
    lines = [f"🌅 DAILY BRIEFING · {date_str}", ""]
    if not summaries:
        lines.append("No active chats in the last 24h.")
    else:
        for item in summaries:
            summary = _clean_summary(item["summary"])
            lines.append(f"*{item['chat_name']} ({item['msg_count']} msgs)*")
            lines.append(summary)
            lines.append("")
    return "\n".join(lines)
