import asyncio

import ultravision.discovery as discovery_module
from ultravision.discovery import VisionModelDiscovery


class _DummyResponse:
    def __init__(self, payload, status=200):
        self.status = 200 if payload is not None else status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self._payload


class _DummySession:
    """Return the same payload for any GET (legacy single-endpoint tests)."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, *args, **kwargs):
        return _DummyResponse(self._payload)


class _RouteSession:
    """Route requests by path suffix and method to canned JSON payloads.

    ``routes`` maps ``(method, path_suffix)`` to a payload; an unmatched route
    responds 404 so the code under test exercises its fallbacks.
    """

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _resolve(self, method, url):
        self.calls.append((method, url))
        for (m, suffix), payload in self.routes.items():
            if m == method and url.endswith(suffix):
                return _DummyResponse(payload)
        return _DummyResponse(None, status=404)

    def get(self, url, **kwargs):
        return self._resolve("GET", url)

    def post(self, url, **kwargs):
        return self._resolve("POST", url)


def _run_fetch(payload):
    discovery = VisionModelDiscovery()
    session = _DummySession(payload)
    return asyncio.run(discovery._fetch_models(session, "http://example"))


def test_fetch_all_models_from_data_key():
    # With no service type, fall back to listing every /v1/models id (any model),
    # rather than filtering by name.
    payload = {
        "data": [
            {"id": "qwen/qwen3-vl-8b"},
            {"id": "some-random-llm"},
        ]
    }
    assert _run_fetch(payload) == ["qwen/qwen3-vl-8b", "some-random-llm"]


def test_fetch_all_models_from_models_key():
    payload = {
        "models": [
            {"id": "llava:13b"},
            {"id": "mistral:7b"},
        ]
    }
    assert _run_fetch(payload) == ["llava:13b", "mistral:7b"]


def test_lmstudio_detects_vision_by_type_not_name():
    # An arbitrarily-named model is detected purely from type == "vlm".
    routes = {
        ("GET", "/api/v0/models"): {
            "data": [
                {"id": "my-custom-multimodal", "type": "vlm"},
                {"id": "plain-text-model", "type": "llm"},
                {"id": "embed-model", "type": "embeddings"},
            ]
        }
    }
    discovery = VisionModelDiscovery()
    session = _RouteSession(routes)
    models = asyncio.run(discovery._fetch_models(session, "http://host:1234", "lm_studio"))
    assert models == ["my-custom-multimodal"]


def test_lmstudio_falls_back_to_all_models_without_native_api():
    # Older LM Studio without /api/v0/models -> list everything from /v1/models.
    routes = {
        ("GET", "/v1/models"): {"data": [{"id": "anything"}, {"id": "another"}]},
    }
    discovery = VisionModelDiscovery()
    session = _RouteSession(routes)
    models = asyncio.run(discovery._fetch_models(session, "http://host:1234", "lm_studio"))
    assert models == ["anything", "another"]


def test_ollama_detects_vision_from_capabilities():
    routes = {
        ("GET", "/api/tags"): {"models": [{"model": "llava:13b"}, {"model": "mistral:7b"}]},
        ("POST", "/api/show"): {"capabilities": ["completion", "vision"]},
    }
    # /api/show returns the same payload for both names here, so both look vision-capable.
    discovery = VisionModelDiscovery()
    session = _RouteSession(routes)
    models = asyncio.run(discovery._fetch_models(session, "http://host:11434", "ollama"))
    assert models == ["llava:13b", "mistral:7b"]


def test_ollama_without_capabilities_lists_all_models():
    # Old Ollama: /api/show has no capabilities field -> surface every tag rather
    # than hide the server.
    routes = {
        ("GET", "/api/tags"): {"models": [{"model": "llava:13b"}, {"model": "qwen2.5vl:7b"}]},
        ("POST", "/api/show"): {"license": "x"},  # no capabilities key
    }
    discovery = VisionModelDiscovery()
    session = _RouteSession(routes)
    models = asyncio.run(discovery._fetch_models(session, "http://host:11434", "ollama"))
    assert sorted(models) == ["llava:13b", "qwen2.5vl:7b"]


def test_address_enumeration_survives_without_psutil(monkeypatch):
    # A missing/broken psutil must not disable discovery: the primary-IP
    # fallback should still yield a routable address (with an assumed /24)
    # so localhost and LAN scanning keep working.
    monkeypatch.setattr(discovery_module, "psutil", None)
    monkeypatch.setattr(VisionModelDiscovery, "_primary_local_ip", staticmethod(lambda: "192.168.1.50"))

    discovery = VisionModelDiscovery()
    addresses = list(discovery._iter_inet_addresses())
    assert ("192.168.1.50", "255.255.255.0") in addresses

    local = discovery._get_local_addresses()
    assert {"127.0.0.1", "localhost", "192.168.1.50"} <= local

    hosts = discovery._get_network_hosts()
    assert "192.168.1.1" in hosts  # derived from the /24 around the primary IP
    assert "192.168.1.50" not in hosts  # own address excluded from the scan


def test_module_imports_when_psutil_missing(monkeypatch):
    # Importing the module must not hard-depend on psutil being installed.
    monkeypatch.setattr(discovery_module, "psutil", None)
    discovery = VisionModelDiscovery()
    # Should not raise even though psutil is unavailable.
    assert isinstance(discovery._get_local_addresses(), set)
