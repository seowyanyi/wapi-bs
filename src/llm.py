import anthropic
import ollama
import os

def call_model(prompt: str, system: str = "") -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic")
    if provider == "local":
        return _call_ollama(prompt, system)
    return _call_anthropic(prompt, system)

def _call_ollama(prompt: str, system: str) -> str:
    model = os.getenv("OLLAMA_MODEL")
    if not model:
        raise ValueError("OLLAMA_MODEL environment variable is not set.")
    
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    response = ollama.chat(model=model, messages=messages)
    return response.message.content

def _call_anthropic(prompt: str, system: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL"),
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
