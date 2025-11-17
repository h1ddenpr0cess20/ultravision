"""Writers for persisting UltraVision responses into multiple formats."""

import json
import csv
from pathlib import Path
from typing import List, Dict, Any

from .api import extract_text

class Writer:
    """Context-managed writer for serializing UltraVision batches.

    Handles JSONL, JSON, plain text, markdown, and CSV output formats by translating
    the same response payload into the desired layout.
    """
    def __init__(self, path: Path, fmt: str):
        self.path = path
        self.fmt = fmt
        self._fp = None
        self._accum = []
        self._csv = None

    def __enter__(self):
        """Prepare the output file and return the writer.

        Returns:
            Writer: Self, ready to write records.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.fmt in ("jsonl", "text", "markdown", "csv"):
            self._fp = self.path.open("w", encoding="utf-8", newline="")
            if self.fmt == "csv":
                self._csv = csv.writer(self._fp)
                self._csv.writerow(["files", "sha256", "mime", "size_bytes", "width", "height", "text"])
        return self

    def write_record(self, files: List[Path], metas: List[Dict[str, Any]], resp: Dict[str, Any]):
        """Persist a single batch's metadata and generated text according to the chosen format.

        Args:
            files (List[Path]): Files that were batched together.
            metas (List[Dict[str, Any]]): Per-file metadata including sha256/mime.
            resp (Dict[str, Any]): Raw LM Studio response to serialize.
        """
        text = extract_text(resp)
        record = {"files": [str(f) for f in files], "text": text, "raw": resp, "meta": metas}
        if self.fmt == "jsonl":
            self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        elif self.fmt == "text":
            self._fp.write(f"# {', '.join(record['files'])}\n{text}\n\n")
        elif self.fmt == "markdown":
            self._fp.write(f"### Files\n- " + "\n- ".join(record["files"]) + "\n\n")
            self._fp.write("### Output\n")
            self._fp.write(text.strip() + "\n\n---\n\n")
        elif self.fmt == "csv":
            m0 = metas[0] if metas else {}
            self._csv.writerow([
                ", ".join(record["files"]),
                m0.get("sha256", ""),
                m0.get("mime", ""),
                m0.get("size_bytes", ""),
                m0.get("width", ""),
                m0.get("height", ""),
                text.replace("\n", " ").strip(),
            ])
        else:  # json
            self._accum.append(record)

    def already_done_hashes(self) -> set:
        """Read an existing jsonl output to avoid reprocessing duplicate images."""
        if not self.path.exists() or self.fmt != "jsonl":
            return set()
        done = set()
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        metas = obj.get("meta") or []
                        for m in metas:
                            if "sha256" in m:
                                done.add(m["sha256"])
                    except Exception:
                        continue
        except Exception:
            pass
        return done

    def __exit__(self, exc_type, exc, tb):
        """Finalize any buffered output and close resources.

        Args:
            exc_type: Exception type if the context exited with an error.
            exc: Exception instance, if any.
            tb: Traceback object if an exception occurred.
        """
        if self.fmt == "json":
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self._accum, f, ensure_ascii=False, indent=2)
        if self._fp:
            self._fp.close()
