from dotenv import load_dotenv

from src.modules import chat_summary
from src.delivery.telegram import send_long_message

load_dotenv()


def main():
    briefing = chat_summary.run(lookback_hours=3)
    print(briefing)
    send_long_message(briefing)


if __name__ == "__main__":
    main()
