import asyncio

from ultravision.discovery import VisionModelDiscovery


class _DummyResponse:
    def __init__(self, payload):
        self.status = 200
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self._payload


class _DummySession:
    def __init__(self, payload):
        self._payload = payload

    def get(self, *args, **kwargs):
        return _DummyResponse(self._payload)


def _run_fetch(payload):
    discovery = VisionModelDiscovery()
    session = _DummySession(payload)
    return asyncio.run(discovery._fetch_models(session, "http://example"))


def test_fetch_models_from_data_key():
    payload = {
        "data": [
            {"id": "qwen/qwen3-vl-8b"},
            {"id": "qwen/qwen3-vl-30b"},
        ]
    }
    models = _run_fetch(payload)
    assert models == ["qwen/qwen3-vl-8b", "qwen/qwen3-vl-30b"]


def test_fetch_models_from_models_key():
    payload = {
        "models": [
            {"id": "qwen/qwen3-vl-8b"},
            {"id": "qwen/qwen3-vl-30b"},
        ]
    }
    models = _run_fetch(payload)
    assert models == ["qwen/qwen3-vl-8b", "qwen/qwen3-vl-30b"]
