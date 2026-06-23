import anthropic


def call_model(prompt: str, system: str = "", model: str = "claude-haiku-4-5") -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
