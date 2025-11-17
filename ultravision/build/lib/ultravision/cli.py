"""Command-line interface glue for UltraVision (batch vision requests and output writers)."""

import argparse
from contextlib import nullcontext
from pathlib import Path
from typing import List

_console = None
HAVE_RICH = False
DEFAULT_OUT_NAME = "outputs"
OUT_EXT_BY_FORMAT = {
    "jsonl": "jsonl",
    "json": "json",
    "text": "txt",
    "markdown": "md",
    "csv": "csv",
}

try:
    from rich.console import Console
    from rich.theme import Theme
    _console = Console(theme=Theme({"ok": "green", "warn": "yellow", "err": "bold red"}))
    HAVE_RICH = True
    def info(msg): _console.log(msg, style="ok")
    def warn(msg): _console.log(msg, style="warn")
    def err(msg):  _console.log(msg, style="err")
except Exception:
    def info(msg): print(msg)
    def warn(msg): print(f"[WARN] {msg}")
    def err(msg):  print(f"[ERROR] {msg}")

from .util import backoff_sleep, run_concurrently
from .images import (
    find_images, load_image_bytes, guess_mime, autorotate_and_resize,
    to_data_url, file_meta, sha256_bytes, make_messages
)
from .writer import Writer
from .api import call_chat_completions

def _prepare_batch(files: List[Path], args):
    """Prepare prompts and metadata for a single batch of images.

    Args:
        files (List[Path]): Image files that will be sent together in one request.
        args: Parsed CLI arguments controlling prompts, rotation, and resizing.

    Returns:
        Tuple[List[dict], List[dict]]: Messages payload plus metadata for each file.
    """
    data_urls = []
    metas = []
    for p in files:
        raw = load_image_bytes(p)
        mime = guess_mime(p)
        if args.autorotate or args.max_side:
            maybe = autorotate_and_resize(p, args.max_side)
            if maybe:
                raw = maybe
        metas.append(file_meta(p, raw))
        data_urls.append(to_data_url(mime, raw))
    messages = make_messages(args.system_prompt, args.prompt, data_urls)
    return messages, metas

def _process_batch(files: List[Path], args):
    """Deliver a prepared batch to the model endpoint with retries.

    Args:
        files (List[Path]): Images already grouped for this batch.
        args: CLI arguments that govern API endpoints, retries, and timeouts.

    Returns:
        dict: Batch result with ``files``, ``metas``, ``resp``, and ``error``.
    """
    messages, metas = _prepare_batch(files, args)
    attempt = 0
    while True:
        try:
            resp = call_chat_completions(
                api_base=args.api_base,
                api_key=args.api_key,
                model=args.model,
                messages=messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                extra=args.extra_dict,
            )
            return {"files": files, "metas": metas, "resp": resp, "error": None}
        except Exception as e:
            if attempt < args.retries:
                attempt += 1
                err(f"Batch error (attempt {attempt}): {e}")
                backoff_sleep(attempt)
                continue
            return {"files": files, "metas": metas, "resp": None, "error": repr(e)}

def main(argv=None):
    """Parse CLI arguments and orchestrate batch processing workflow.

    Args:
        argv (Sequence[str] | None): Override for CLI arguments passed from ``sys.argv``.

    Returns:
        int: Exit code where 0 means success and 2 indicates user-facing errors.
    """
    ap = argparse.ArgumentParser(
        description="Ultra image processor for LM Studio + Qwen3-VL: fast, parallel, robust."
    )
    ap.add_argument("directory", type=Path, help="Directory containing images.")
    ap.add_argument("--model", default="qwen/qwen3-vl-8b", help="LM Studio model id (e.g., qwen/qwen3-vl-8b).")
    ap.add_argument("--api-base", default="http://localhost:1234", help="LM Studio base URL (no /v1).")
    ap.add_argument("--api-key", default="lm-studio", help="Bearer token header (LM Studio ignores value).")

    ap.add_argument("--prompt", default="Describe the image succinctly with key details.", help="User prompt.")
    ap.add_argument("--system-prompt", default="You are a precise, concise vision assistant.", help="System prompt.")
    ap.add_argument("--per-request", type=int, default=1, help="Images per API request (1..N).")
    ap.add_argument("--recursive", action="store_true", help="Scan subfolders.")
    ap.add_argument("--patterns", nargs="*", help="Glob patterns (e.g., *.png *.jpg).")
    ap.add_argument("--limit", type=int, default=None, help="Max total images to process.")
    ap.add_argument("--resume", action="store_true", help="Skip images already in JSONL (by sha256).")

    ap.add_argument("--format", choices=["jsonl", "json", "text", "csv", "markdown"], default="jsonl",
                    help="Output format (default: jsonl).")
    ap.add_argument("--out", default=None, help="Output file path (defaults to outputs.<format>).")
    ap.add_argument("--fail-log", default="failures.log", help="Where to log failed batches.")

    ap.add_argument("--max-tokens", type=int, default=3000, help="Max tokens for model output.")
    ap.add_argument("--temperature", type=float, default=0.2, help="Temperature.")
    ap.add_argument("--timeout", type=int, default=90, help="HTTP timeout seconds.")
    ap.add_argument("--retries", type=int, default=5, help="Retries on errors.")

    ap.add_argument("--extra", default=None, help='Extra JSON merged into request body (e.g. {"top_p":0.9}).')

    ap.add_argument("--concurrency", type=int, default=2, help="Concurrent API calls.")
    ap.add_argument("--autorotate", action="store_true", help="Autorotate via EXIF (requires Pillow).")
    ap.add_argument("--max-side", type=int, default=None,
                    help="If set, resize so max(width,height) <= this (requires Pillow).")

    args = ap.parse_args(argv)

    if not args.out:
        ext = OUT_EXT_BY_FORMAT.get(args.format, args.format)
        args.out = f"{DEFAULT_OUT_NAME}.{ext}"

    # Parse extras
    args.extra_dict = None
    if args.extra:
        import json
        try:
            args.extra_dict = json.loads(args.extra)
            if not isinstance(args.extra_dict, dict):
                raise ValueError("extra must be a JSON object")
        except Exception as e:
            err(f"Invalid --extra JSON: {e}")
            return 2

    # Collect files
    root = args.directory
    if not root.exists() or not root.is_dir():
        err(f"{root} is not a directory.")
        return 2

    all_images = find_images(root, args.recursive, args.patterns)
    if args.limit:
        all_images = all_images[:args.limit]
    if not all_images:
        warn("No matching images found.")
        return 0

    # Prepare writer & resume filter
    writer = Writer(Path(args.out), args.format)
    done_hashes = set()
    if args.resume and args.format == "jsonl":
        done_hashes = writer.already_done_hashes()
        if done_hashes:
            info(f"Resume enabled: {len(done_hashes)} already in {args.out}, will skip duplicates.")

    with writer:
        # Build batches with dedup by file content
        batches = []
        seen_hashes = set(done_hashes)
        chunk = []
        for p in all_images:
            try:
                b = load_image_bytes(p)
                h = sha256_bytes(b)
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                chunk.append(p)
                if len(chunk) >= max(1, args.per_request):
                    batches.append(chunk)
                    chunk = []
            except Exception as e:
                warn(f"Skipping unreadable {p}: {e}")
        if chunk:
            batches.append(chunk)

        # Progress spinner (falls back to no spinner if rich is unavailable)
        total_batches = len(batches)
        processed_batches = 0
        fails = []
        status_cm = _console.status(
            f"Processing batches (0/{total_batches})", spinner="dots"
        ) if HAVE_RICH and total_batches else nullcontext()

        with status_cm as status:
            # Run concurrently
            def on_result(res):
                nonlocal processed_batches
                if res["error"] or res["resp"] is None:
                    fails.append({"files": [str(f) for f in res["files"]], "error": res["error"]})
                    err(f"Batch failed: {res['error']}")
                else:
                    writer.write_record(res["files"], res["metas"], res["resp"])
                    info(f"✓ {len(res['files'])} image(s) processed")

                processed_batches += 1
                if status is not None:
                    status.update(f"Processing batches ({processed_batches}/{total_batches})")

            jobs = [(batch, args) for batch in batches]
            run_concurrently(_process_batch, jobs, max_workers=max(1, args.concurrency), on_result=on_result)

            if status is not None:
                status.update("Processing batches (complete)")

        if fails:
            fail_path = Path(args.fail_log)
            with fail_path.open("w", encoding="utf-8") as f:
                import json as _json
                for rec in fails:
                    f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
            warn(f"{len(fails)} batch(es) failed. See {fail_path}")

    info(f"✅ Done. Results → {args.out} ({args.format})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
