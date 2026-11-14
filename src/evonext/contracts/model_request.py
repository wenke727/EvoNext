"""Pure Chat Completions request shape shared by preview and transport."""

def chat_payload(model, messages, max_tokens, temperature=None, reasoning_effort=None):
    # Sol's Chat Completions API rejects the legacy max_tokens parameter.
    sol = model == "gpt-6.1-sol" or model.startswith("gpt-6.1-sol-")
    token_key = "max_completion_tokens" if sol else "max_tokens"
    payload = {"model": model, "messages": messages, token_key: max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    return payload


