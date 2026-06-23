"""
Chat summary module.

Per active chat: fetch messages (floor of last 10) → one LLM call → summary.
Routing into sections + the final briefing layout come in later steps; for now
we render a flat list so the pipeline stays runnable.
"""

from datetime import datetime, timedelta, timezone

from src.llm.client import call_model
from src.context_loader import load_personal_context, load_chat_context
from src.db.reader import (
    fetch_active_chats,
    fetch_chat_messages,
    load_excluded_chats,
)


def run(lookback_hours: int = 24) -> str:
    """Fetch active chats, summarise each via LLM, and return a formatted briefing."""
    excluded_chats = load_excluded_chats()
    chats = fetch_active_chats(lookback_hours, excluded_chats)
    personal_context = load_personal_context()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")

    print(f"\nFound {len(chats)} active chats in the last {lookback_hours}h\n")
    if personal_context:
        print("Personal context loaded.\n")

    summaries = []
    for chat in chats:
        chat_name = chat["chat_name"] or chat["chat_jid"]
        messages = fetch_chat_messages(chat["chat_jid"], lookback_hours)
        print(f"--- {chat_name} [{chat['chat_jid']}] ({len(messages)} fetched) ---")
        transcript = format_transcript(messages, cutoff)
        chat_context = load_chat_context(chat["chat_jid"])
        summary = _summarise_chat(chat_name, transcript, personal_context, chat_context)
        window_count = sum(1 for m in messages if m["timestamp"] >= cutoff)
        summaries.append({
            "chat_jid": chat["chat_jid"],
            "chat_name": chat_name,
            "is_group": chat["is_group"],
            "msg_count": window_count,
            "summary": summary,
        })

    summaries.sort(key=lambda x: x["msg_count"], reverse=True)
    return render_briefing(summaries)


def format_transcript(messages: list[dict], cutoff: str | None = None) -> str:
    """Format messages as a readable transcript for the LLM.

    When `cutoff` is provided, the transcript is split into two labelled
    sections so the LLM knows which messages are new vs. background context.
    """
    if cutoff:
        context_msgs = [m for m in messages if m["timestamp"] < cutoff]
        new_msgs = [m for m in messages if m["timestamp"] >= cutoff]
        lines = []
        if context_msgs:
            lines.append("## EARLIER CONTEXT (use as background context only — do not treat this as new updates for today.)")
            lines.extend(_format_message(m) for m in context_msgs)
        lines.append("\n## NEW SINCE YESTERDAY (Focus only on this section to summarise.)")
        if new_msgs:
            lines.extend(_format_message(m) for m in new_msgs)
        else:
            lines.append("(no new messages)")
        return "\n".join(lines)
    return "\n".join(_format_message(m) for m in messages)


def _format_message(m: dict) -> str:
    sender = "Me" if m["is_from_me"] else (m["sender_display"] or m["sender"] or "Unknown")
    ts = m["timestamp"][:16]  # "YYYY-MM-DD HH:MM"
    content = m["content_display"] or m["content"] or "[media]"
    return f"[{ts}] {sender}: {content}"


def _summarise_chat(
    chat_name: str,
    transcript: str,
    personal_context: str = "",
    chat_context: str = "",
) -> str:
    """Summarise one chat via the LLM, returning a free-form summary string."""
    system = """
    You are Yan Yi's personal daily WhatsApp intelligence briefing assistant.

    The transcript is split into two sections:
    - EARLIER CONTEXT: older messages provided as background. Read them to understand the conversation, but do not report on them.
    - NEW SINCE YESTERDAY: the messages to summarise.

    Produce a concise summary (no more than 3 sentences) of the key points, decisions, and action items from the NEW SINCE YESTERDAY section only. Use EARLIER CONTEXT solely to interpret the new messages.

    Write in a clear, concise manner. Use bullet points for readability.

    Do not include a title or the chat name — go straight into the content.
    Do not include any preamble, introductory sentences, or meta-commentary about what you are doing. No phrases like "Here's a summary of...", "The following are...", or similar. Output only the summary content itself, starting immediately with the first point.    
    """.strip()

    if personal_context:
        system += f"\n\n## About Yan Yi\n{personal_context}"

    user_prompt = f"Transcript of the chat named '{chat_name}':\n\n{transcript}\n"
    if chat_context:
        user_prompt += f"\n## Context about this chat\n{chat_context}\n"

    return call_model(user_prompt, system=system).strip()


def _clean_summary(text: str) -> str:
    """Sanitize LLM output for Telegram Markdown rendering.

    - Converts **bold** → *bold* (Telegram Markdown uses single asterisks).
    - Converts markdown list bullets (* / - / +) → • so they aren't
      misread as bold/italic delimiters by Telegram's parser.
    """
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"^(\s*)[*\-+]\s+", r"\1• ", text, flags=re.MULTILINE)
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
