"""
- Summarise all active group chats with messages in the last 24 hours
- Summarise active individual chats in the same timeframe
- LLM flags anything requiring your attention or action
- Pushed to Telegram as a digest
"""

import src.llm.client
from src.db.reader import fetch_messages_by_time_window, load_excluded_chats

def run(lookback_hours: int) -> str:
    """Summarise active group and individual chats from the last `lookback_hours`.

    Returns a formatted string ready for delivery.
    """
    # get chat messages
    excluded_chats = load_excluded_chats()
    print(f"Excluding chats: {excluded_chats}")
    chat_messages = fetch_messages_by_time_window(lookback_hours, excluded_chats=excluded_chats)
    return chat_messages
    # pass into call model and ask it to summarise
