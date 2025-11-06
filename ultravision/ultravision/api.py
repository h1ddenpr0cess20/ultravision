import json
import requests

def call_chat_completions(
    api_base: str,
    api_key: str,
    model: str,
    messages,
    temperature: float,
    max_tokens: int,
    timeout: int,
    extra: dict | None = None,
):
    # Call OpenAI-compatible Chat Completions at {api_base}/v1/chat/completions.
    # Intended for LM Studio but should work with any compatible server.
    url = api_base.rstrip("/") + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key or 'lm-studio'}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    if extra:
        body.update(extra)
    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=timeout)
    if resp.status_code >= 400:
        raise requests.HTTPError(f"{resp.status_code} {resp.reason}: {resp.text[:400]}", response=resp)
    return resp.json()

def extract_text(resp: dict) -> str:
    choice = (resp.get("choices") or [{}])[0]
    if isinstance(choice.get("message"), dict):
        return choice["message"].get("content") or ""
    return choice.get("text", "") or ""
