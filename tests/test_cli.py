from __future__ import annotations

import json

from ultravision import cli


def test_cli_processes_images_and_deduplicates(tmp_path, image_factory, monkeypatch):
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    img_a = image_factory(images_dir / "a.png")
    image_factory(images_dir / "b.png", size=(16, 16))
    dup = images_dir / "dup.png"
    dup.write_bytes(img_a.read_bytes())

    out_path = tmp_path / "results.jsonl"
    calls = []

    def fake_chat_call(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": f"resp {len(calls)}"}}]}

    monkeypatch.setattr(cli, "call_chat_completions", fake_chat_call)

    rc = cli.main(
        [
            str(images_dir),
            "--out",
            str(out_path),
            "--per-request",
            "1",
            "--concurrency",
            "1",
        ]
    )
    assert rc == 0
    assert len(calls) == 2  # third image is a duplicate and skipped

    lines = [line for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    payloads = [json.loads(line) for line in lines]
    assert payloads[0]["files"]
    assert all("text" in p for p in payloads)


def test_cli_rejects_invalid_extra(tmp_path):
    rc = cli.main([str(tmp_path), "--extra", "{not json}"])
    assert rc == 2


def test_cli_auto_discover_picks_first_target(tmp_path, image_factory, monkeypatch):
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    image_factory(images_dir / "a.png")

    out_path = tmp_path / "results.jsonl"
    calls = []

    def fake_chat_call(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    class DummyDiscovery:
        def __init__(self, **_kwargs):
            pass

        async def discover(self):
            return {
                "lm_studio": [
                    {
                        "server_address": "http://10.0.0.5:7777",
                        "vision_models": ["autopilot"],
                        "local_addresses": ["http://localhost:7777"],
                    }
                ],
                "ollama": [],
            }

    monkeypatch.setattr(cli, "call_chat_completions", fake_chat_call)
    monkeypatch.setattr(cli, "VisionModelDiscovery", DummyDiscovery)

    rc = cli.main([str(images_dir), "--out", str(out_path), "--auto-discover", "--concurrency", "1"])
    assert rc == 0
    assert calls and calls[0]["api_base"] == "http://10.0.0.5:7777"
    assert calls[0]["model"] == "autopilot"
