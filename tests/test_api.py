from __future__ import annotations

from ultravision import api


def test_extract_text_prefers_message_content():
    resp = {"choices": [{"message": {"content": "hello"}}]}
    assert api.extract_text(resp) == "hello"


def test_extract_text_falls_back_to_text_key():
    resp = {"choices": [{"text": "fallback"}]}
    assert api.extract_text(resp) == "fallback"
