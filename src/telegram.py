import os

import requests


TELEGRAM_API_BASE = "https://api.telegram.org"


def send_message(text: str, parse_mode: str = "Markdown") -> dict:
    """Send a text message to the configured Telegram chat.

    Args:
        text: Message body. Supports Markdown by default.
        parse_mode: 'Markdown', 'MarkdownV2', or 'HTML'.

    Returns:
        The Telegram API response as a dict.

    Raises:
        requests.HTTPError: If the request fails or Telegram returns an error.
        KeyError: If TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars are missing.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def send_long_message(text: str, chunk_size: int = 4096, parse_mode: str = "Markdown") -> list[dict]:
    """Split a long message into chunks and send each to Telegram.

    Telegram's maximum message length is 4096 characters.

    Returns:
        List of Telegram API responses, one per chunk.
    """
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    return [send_message(chunk, parse_mode=parse_mode) for chunk in chunks]
