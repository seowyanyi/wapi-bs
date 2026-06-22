from collections import Counter

from dotenv import load_dotenv

from src.modules import chat_summary

load_dotenv()


def main():
    messages = chat_summary.run(lookback_hours=24)

    # Aggregate: preserve first-seen chat_name per jid, count messages
    names = {}
    counts = Counter()
    for m in messages:
        jid = m["chat_jid"]
        if jid not in names:
            names[jid] = m["chat_name"] or ""
        counts[jid] += 1

    # Sort by message count descending
    rows = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    col_jid = max((len(jid) for jid in names), default=8)
    col_name = max((len(n) for n in names.values()), default=9)
    header = f"{'JID':<{col_jid}}  {'Chat name':<{col_name}}  Messages"
    print(header)
    print("-" * len(header))
    for jid, count in rows:
        print(f"{jid:<{col_jid}}  {names[jid]:<{col_name}}  {count}")


if __name__ == "__main__":
    main()
