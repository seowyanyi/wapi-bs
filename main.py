import time
import os
from dotenv import load_dotenv

from src import chat_summary
from src.telegram import send_long_message

load_dotenv()


def main():
    provider = os.getenv("LLM_PROVIDER", "anthropic")
    if provider == "local":
        model = os.getenv("OLLAMA_MODEL")
    else:
        model = os.getenv("ANTHROPIC_MODEL")

    start = time.perf_counter()
    briefing = chat_summary.run(lookback_hours=24)
    elapsed = time.perf_counter() - start
    print(f"{model}: [chat_summary] completed in {elapsed:.2f}s")
    print(briefing)
    send_long_message(briefing)


if __name__ == "__main__":
    main()
