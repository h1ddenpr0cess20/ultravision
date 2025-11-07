from __future__ import annotations

import csv
import json
from pathlib import Path

from ultravision.writer import Writer


def sample_response(text: str = "a description") -> dict:
    return {"choices": [{"message": {"content": text}}]}


def test_writer_jsonl_and_resume(tmp_path):
    out = tmp_path / "out.jsonl"
    writer = Writer(out, "jsonl")
    metas = [{"sha256": "abc123", "mime": "image/png"}]
    files = [Path("image.png")]

    with writer:
        writer.write_record(files, metas, sample_response("first"))

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["files"] == [str(files[0])]
    assert payload["meta"][0]["sha256"] == "abc123"
    assert payload["text"] == "first"

    resume_hashes = writer.already_done_hashes()
    assert resume_hashes == {"abc123"}


def test_writer_text_format(tmp_path):
    out = tmp_path / "out.txt"
    with Writer(out, "text") as writer:
        writer.write_record(
            [Path("one.png")],
            [{"sha256": "abc"}],
            sample_response("line1\nline2"),
        )
    contents = out.read_text(encoding="utf-8")
    assert "# one.png" in contents
    assert "line1" in contents and "line2" in contents


def test_writer_markdown_format(tmp_path):
    out = tmp_path / "doc.md"
    with Writer(out, "markdown") as writer:
        writer.write_record(
            [Path("one.png"), Path("two.png")],
            [{"sha256": "abc"}],
            sample_response("markdown body"),
        )
    md = out.read_text(encoding="utf-8")
    assert "### Files" in md
    assert "- one.png" in md and "- two.png" in md
    assert "### Output" in md


def test_writer_csv_format(tmp_path):
    out = tmp_path / "rows.csv"
    with Writer(out, "csv") as writer:
        writer.write_record(
            [Path("img.png")],
            [
                {
                    "sha256": "hash",
                    "mime": "image/png",
                    "size_bytes": 42,
                    "width": 10,
                    "height": 5,
                }
            ],
            sample_response("value\nwith break"),
        )
    with out.open(newline="", encoding="utf-8") as fp:
        reader = list(csv.reader(fp))
    assert reader[0] == ["files", "sha256", "mime", "size_bytes", "width", "height", "text"]
    assert reader[1][0] == "img.png"
    assert reader[1][-1] == "value with break"


def test_writer_json_format(tmp_path):
    out = tmp_path / "records.json"
    writer = Writer(out, "json")
    with writer:
        writer.write_record([Path("img.png")], [{"sha256": "abc"}], sample_response("json text"))
        writer.write_record([Path("img2.png")], [{"sha256": "def"}], sample_response("json text 2"))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert payload[0]["files"] == ["img.png"]
    assert payload[1]["text"] == "json text 2"


def test_already_done_hashes_tolerates_invalid_lines(tmp_path):
    out = tmp_path / "bad.jsonl"
    out.write_text('{"meta":[{"sha256":"ok"}]}\nnot json\n{"meta":[{}]}\n', encoding="utf-8")
    writer = Writer(out, "jsonl")
    assert writer.already_done_hashes() == {"ok"}
