"""
Stage 1: active chats → one LLM call per chat → flat list → Telegram.
"""

from datetime import datetime, timezone

from src.llm.client import call_model
from src.db.reader import fetch_messages_by_time_window, load_excluded_chats

def run(lookback_hours: int = 24) -> str:
    """Fetch active chats, summarise each via LLM, and return a formatted briefing."""
    excluded_chats = load_excluded_chats()
    messages = fetch_messages_by_time_window(lookback_hours, excluded_chats)

    grouped = group_by_chat(messages)

    summaries = []
    for jid, msgs in grouped.items():
        chat_name = msgs[0]["chat_name"] or jid
        print(f"Processing chat {chat_name} with {jid=}")
        transcript = format_transcript(msgs)
        summary = _summarise_chat(chat_name, transcript)
        summaries.append({
            "chat_name": chat_name,
            "msg_count": len(msgs),
            "summary": summary,
        })

    summaries.sort(key=lambda x: x["msg_count"], reverse=True)
    return render_briefing(summaries)

def group_by_chat(messages: list[dict]) -> dict[str, list[dict]]:
    """Group a flat message list by chat_jid, preserving insertion order."""
    grouped: dict[str, list[dict]] = {}
    for msg in messages:
        grouped.setdefault(msg["chat_jid"], []).append(msg)
    return grouped


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
    """Call LLM to produce a one-line summary of a single chat.

    Fill in the prompt below, then run a real API call to verify before wiring tests.
    """
    # print(f"Summarising chat {chat_name} with {len(transcript)} chars of transcript...")
    # print("\n\n")
    # print(transcript)
    system = "You are Yan Yi's personal daily intelligence briefing assistant. Your job is to process his WhatsApp messages from the past 24 hours and produce a structured, actionable briefing he can read in under 3 minutes on Telegram. You will be given a transcript of messages from a single chat. Your task is to summarise the key points, decisions, and action items in a concise manner. The summary should be no more than 3 sentences long, and should be written in a clear, professional tone. Avoid including any irrelevant information or personal opinions. Focus on what is important for Yan Yi to know and act upon. Do not include a title or heading that identifies the chat name — go straight into the content. You may use bold labels for sections like Key Points or Action Items."
    
    user_prompt = f"Here is the transcript of messages from the chat named '{chat_name}':\n\n{transcript}\n\n"
    return call_model(user_prompt, system=system)


def _clean_summary(text: str) -> str:
    """Sanitize LLM output for Telegram Markdown rendering.

    - Converts **bold** → *bold* (Telegram Markdown uses single asterisks).
    """
    import re
    # ** → * for Telegram bold
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    return text


def render_briefing(summaries: list[dict], now: datetime | None = None) -> str:
    """Render a flat briefing string.

    Each entry in `summaries` must have: chat_name (str), msg_count (int), summary (str).
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
