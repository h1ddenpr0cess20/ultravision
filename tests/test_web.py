from __future__ import annotations

import pytest

from ultravision.web import server


def test_web_main_parses_args(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "run", lambda **kwargs: captured.update(kwargs))

    server.main(["--host", "127.0.0.1", "--port", "9001", "--reload"])

    assert captured == {"host": "127.0.0.1", "port": 9001, "reload": True}


def test_web_main_defaults_are_production_safe(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "run", lambda **kwargs: captured.update(kwargs))

    server.main([])

    # Reload must default off so the shipped console script / container does not
    # start uvicorn's dev file-watcher.
    assert captured == {"host": "0.0.0.0", "port": 8000, "reload": False}


def test_web_run_signature_defaults():
    import inspect

    defaults = {
        name: param.default
        for name, param in inspect.signature(server.run).parameters.items()
    }
    assert defaults == {"host": "0.0.0.0", "port": 8000, "reload": False}


def test_web_main_rejects_bad_port():
    with pytest.raises(SystemExit):
        server.main(["--port", "not-a-number"])
