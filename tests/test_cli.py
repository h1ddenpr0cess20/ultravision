from __future__ import annotations

import json

import pytest
import requests

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


def test_cli_resume_preserves_existing_and_skips_done(tmp_path, image_factory, monkeypatch):
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    image_factory(images_dir / "a.png")
    out_path = tmp_path / "results.jsonl"

    calls = []

    def fake_chat_call(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": f"resp {len(calls)}"}}]}

    monkeypatch.setattr(cli, "call_chat_completions", fake_chat_call)

    base_args = [str(images_dir), "--out", str(out_path), "--concurrency", "1"]

    # First pass processes the single image.
    assert cli.main(base_args) == 0
    assert len(calls) == 1

    # Add a second image, then resume: the first must be skipped and its record
    # preserved (the writer must not truncate the existing output).
    image_factory(images_dir / "b.png", size=(16, 16))
    assert cli.main(base_args + ["--resume"]) == 0
    assert len(calls) == 2  # only the new image triggered a call

    lines = [line for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2  # original record survived alongside the new one


def test_cli_rejects_invalid_extra(tmp_path):
    rc = cli.main([str(tmp_path), "--extra", "{not json}"])
    assert rc == 2


def test_cli_fails_fast_on_non_retryable_error(tmp_path, image_factory, monkeypatch):
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    image_factory(images_dir / "a.png")
    out_path = tmp_path / "results.jsonl"

    attempts = []

    class _Resp:
        status_code = 400

    def fake_chat_call(**kwargs):
        attempts.append(kwargs)
        raise requests.HTTPError("400 Bad Request", response=_Resp())

    slept = []
    monkeypatch.setattr(cli, "call_chat_completions", fake_chat_call)
    monkeypatch.setattr(cli, "backoff_sleep", lambda attempt: slept.append(attempt))

    rc = cli.main(
        [
            str(images_dir),
            "--out",
            str(out_path),
            "--concurrency",
            "1",
            "--retries",
            "5",
            "--fail-log",
            str(tmp_path / "failures.log"),
        ]
    )

    assert rc == 0  # run completes; the batch is logged as a failure
    assert len(attempts) == 1  # a 400 is not retried despite --retries 5
    assert slept == []  # and no backoff was spent


def test_cli_retries_transient_error(tmp_path, image_factory, monkeypatch):
    images_dir = tmp_path / "imgs"
    images_dir.mkdir()
    image_factory(images_dir / "a.png")
    out_path = tmp_path / "results.jsonl"

    class _Resp:
        status_code = 503

    attempts = {"n": 0}

    def flaky_chat_call(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise requests.HTTPError("503", response=_Resp())
        return {"choices": [{"message": {"content": "recovered"}}]}

    monkeypatch.setattr(cli, "call_chat_completions", flaky_chat_call)
    monkeypatch.setattr(cli, "backoff_sleep", lambda attempt: None)

    rc = cli.main(
        [str(images_dir), "--out", str(out_path), "--concurrency", "1", "--retries", "5"]
    )

    assert rc == 0
    assert attempts["n"] == 2  # failed once, retried, then succeeded
    lines = [ln for ln in out_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert json.loads(lines[0])["text"] == "recovered"


def test_cli_version_flag(capsys):
    from ultravision import __version__

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


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
