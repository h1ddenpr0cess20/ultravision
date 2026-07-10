from __future__ import annotations

import pytest
import requests

from ultravision import api


def test_extract_text_prefers_message_content():
    resp = {"choices": [{"message": {"content": "hello"}}]}
    assert api.extract_text(resp) == "hello"


def test_extract_text_falls_back_to_text_key():
    resp = {"choices": [{"text": "fallback"}]}
    assert api.extract_text(resp) == "fallback"


def test_extract_text_handles_empty_response():
    assert api.extract_text({}) == ""
    assert api.extract_text({"choices": [{"message": {"content": None}}]}) == ""


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, reason="OK", text=""):
        self.status_code = status_code
        self.reason = reason
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_call_chat_completions_builds_request(monkeypatch):
    """A trailing slash is normalized and an empty key falls back to the placeholder."""
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json, timeout=timeout)
        return _FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(api.requests, "post", fake_post)

    resp = api.call_chat_completions(
        api_base="http://host:1234/",
        api_key="",
        model="qwen/qwen3-vl-8b",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
        max_tokens=128,
        timeout=30,
        extra={"top_p": 0.9},
    )

    assert resp == {"choices": [{"message": {"content": "ok"}}]}
    assert captured["url"] == "http://host:1234/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer lm-studio"
    assert captured["timeout"] == 30
    assert captured["body"]["model"] == "qwen/qwen3-vl-8b"
    assert captured["body"]["max_tokens"] == 128
    assert captured["body"]["top_p"] == 0.9


def _http_error(status_code):
    resp = _FakeResponse(status_code=status_code, reason="x", text="x")
    return requests.HTTPError("boom", response=resp)


@pytest.mark.parametrize("status", [429, 408, 500, 502, 503, 504])
def test_is_retryable_error_transient_statuses(status):
    assert api.is_retryable_error(_http_error(status)) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_is_retryable_error_client_statuses(status):
    assert api.is_retryable_error(_http_error(status)) is False


def test_is_retryable_error_network_and_unknown():
    """An HTTPError without a response is transient; programming errors fail fast."""
    assert api.is_retryable_error(requests.Timeout()) is True
    assert api.is_retryable_error(requests.ConnectionError()) is True
    assert api.is_retryable_error(requests.HTTPError("no response")) is True
    assert api.is_retryable_error(ValueError("bug")) is False
    assert api.is_retryable_error(KeyError("bug")) is False


def test_call_chat_completions_raises_on_http_error(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return _FakeResponse(status_code=500, reason="Server Error", text="boom")

    monkeypatch.setattr(api.requests, "post", fake_post)

    with pytest.raises(requests.HTTPError) as excinfo:
        api.call_chat_completions(
            api_base="http://host:1234",
            api_key="k",
            model="m",
            messages=[],
            temperature=0.0,
            max_tokens=10,
            timeout=5,
        )
    assert "500" in str(excinfo.value)
