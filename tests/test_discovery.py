import asyncio

import ultravision.discovery as discovery_module
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
