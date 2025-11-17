"""Helpers for calling LM Studio/OpenAI-compatible chat completions."""

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
    """Call an OpenAI-compatible chat completion endpoint.

    Args:
        api_base (str): Base URL for the API (without ``/v1`` suffix).
        api_key (str): Bearer token for authorization.
        model (str): Model identifier (e.g., ``qwen/qwen3-vl-8b``).
        messages: Prebuilt chat messages payload.
        temperature (float): Sampling temperature.
        max_tokens (int): Token budget for generated text.
        timeout (int): Seconds before the HTTP request times out.
        extra (dict | None): Additional fields merged into the request body.

    Returns:
        dict: Parsed JSON response from the server.

    Raises:
        requests.HTTPError: When the remote service responds with a 4xx/5xx status.
    """
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
    """Extract the assistant text from a chat completions response.

    Args:
        resp (dict): Raw response returned by ``requests``.

    Returns:
        str: The first assistant message text, or an empty string if absent.
    """
    choice = (resp.get("choices") or [{}])[0]
    if isinstance(choice.get("message"), dict):
        return choice["message"].get("content") or ""
    return choice.get("text", "") or ""
