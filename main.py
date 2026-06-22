from dotenv import load_dotenv
from src.modules import chat_summary

load_dotenv()


def main():
    result = chat_summary.run(lookback_hours=24)
    print(result)


if __name__ == "__main__":
    main()
