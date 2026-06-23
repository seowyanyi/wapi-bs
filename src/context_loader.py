"""Load optional private context files for LLM prompts."""

import tomllib
from pathlib import Path

_CONTEXT_DIR = Path("context")
_CHATS_TOML = _CONTEXT_DIR / "chats.toml"


def _load_chats_config() -> dict:
    if not _CHATS_TOML.exists():
        return {}
    with open(_CHATS_TOML, "rb") as f:
        return tomllib.load(f)


def load_personal_context() -> str:
    """Return personal context string, or empty string if file is absent."""
    path = _CONTEXT_DIR / "personal.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_chat_context(chat_jid: str) -> str:
    """Return concatenated context for all tags assigned to chat_jid.

    chats.toml structure:
        [tags]
        LYM = "context/lym.md"
        PT  = "context/production.md"

        [chats]
        "1234567890-1234567890@g.us" = ["LYM", "PT"]
        "6512345678@s.whatsapp.net"  = ["LYM"]
    """
    config = _load_chats_config()
    tag_files: dict[str, str] = config.get("tags", {})
    chat_tags = config.get("chats", {}).get(chat_jid, [])

    if isinstance(chat_tags, str):
        chat_tags = [chat_tags]

    chunks = []
    for tag in chat_tags:
        file_path = tag_files.get(tag)
        if not file_path:
            continue
        p = Path(file_path)
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8").strip()
        chunks.append(content)

    return "\n\n".join(chunks)
