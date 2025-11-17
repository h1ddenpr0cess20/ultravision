# UltraVision

UltraVision is a fast, resilient batch image processor that pairs LM Studio (or any OpenAI-compatible vision model) with a CLI + web companion. Run it locally to describe folders of images, resume interrupted runs, deduplicate by hash, or spin up a browser-based studio for drag-and-drop uploads.

## Features

- **Batch pipelines:** Recursive scans, glob filters, per-request batching, resume/deduplication, smart retries with backoff, and concurrency controls.
- **Multi-format outputs:** JSONL, JSON, plain text, Markdown, and CSV writers share a common extraction pipeline.
- **Auto-discovery:** Optional LAN scan for LM Studio/Ollama servers to pre-fill `api_base` and select a vision-capable model.
- **Web studio:** FastAPI-backed browser UI for drag-and-drop uploads that reuses the same helpers as the CLI.
- **Docker-friendly:** Official image with entrypoints for both the CLI and web companion.

## Requirements

- Python 3.9+ (as declared in `ultravision/pyproject.toml`).
- A running LM Studio instance or other OpenAI-compatible vision server that exposes `/v1/models` and `/v1/chat/completions` for vision models (e.g., Qwen3-VL).
- Optional extras: Pillow for EXIF autorotate/resize, `rich` for colored logs, and FastAPI/uvicorn for the web companion (installed with the base package).

## Getting started

1. **Install the package**
   ```bash
   pip install .
   ```
   (Or build a wheel via `python -m build` and `pip install ./dist/ultravision-*.whl`.)

   For development:
   ```bash
   pip install -e ".[dev]"
   ```

2. **Start LM Studio** (default `http://localhost:1234`) with `qwen/qwen3-vl-8b` or another vision-enabled model.

3. **Run UltraVision**
   ```bash
   ultravision ./images --model qwen/qwen3-vl-8b --format jsonl --out results.jsonl
   ```

   Or let UltraVision auto-discover LM Studio/Ollama servers and pick a vision model for you:
   ```bash
   ultravision ./images --auto-discover --format jsonl --out results.jsonl
   ```

UltraVision autodetects common image extensions, batches requests, retries failures with backoff, and writes the outputs in the format you choose.

## Command-line highlights

- **Batching & resuming:** `--per-request`, `--limit`, `--recursive`, `--patterns`, and `--concurrency` tune how images are grouped. `--resume` plus `--format jsonl` loads previously written SHA-256 hashes to skip duplicates.
- **Outputs:** Supported formats are `jsonl`, `json`, `text`, `markdown`, or `csv`; the CLI defaults to `outputs.<format>`.
- **Prompt control:** Customize `--system-prompt`, `--prompt`, temperature, `--max-tokens`, and inject arbitrary JSON with `--extra` (e.g., `{"top_p":0.9}`).
- **Auto discovery:** `--auto-discover` scans for LM Studio/Ollama servers and selects the first vision-ready model; adjust the behavior with `--prefer-service`, custom ports, and `--discovery-models`.
- **Image hygiene:** Add `--autorotate` and `--max-side` (Pillow) to normalize EXIF orientation and limit the largest dimension before uploading.
- **Failure visibility:** Colored logging via `rich` (when available) plus `--fail-log` captures batches that exhaust retries.

Example workflows:

```bash
ultravision ./images --per-request 2 --concurrency 4 --autorotate --max-side 1600
ultravision ./images --resume --format markdown --out summary.md
ultravision ./images --format csv --out spreadsheet.csv
ultravision ./images --auto-discover --format jsonl --out discovered.jsonl
```

Run `ultravision --help` to explore every flag documented in `docs/cli.md`.

## Web studio

FastAPI backs the browser UI:

```bash
pip install .
uvicorn ultravision.web.server:app --reload
```

Open [http://localhost:8000](http://localhost:8000), drag images into the page, and point the settings at your LM Studio endpoint. The server reuses the same helpers as the CLI so metadata, prompts, and output extraction stay consistent.

You can also use the packaged entry point, which wraps uvicorn for you:

```bash
ultravision-web --host 0.0.0.0 --port 8000
```

UltraVision Studio pings `/api/discover` on load so the **Server** and **Model** dropdowns are pre-filled with any LM Studio or Ollama hosts on your network. Use the Refresh button to rescan or flip either control to **Custom** when you need to override the discovered values.

## Docker

Build the official container once from the repository root:

```bash
docker build -t ultravision .
```

Run the CLI by mounting your image directory(s) and wherever you want the outputs to land. The container defaults to the CLI entry point, so any argument you pass will be forwarded to `ultravision`:

```bash
docker run --rm -it \
  -v "$(pwd)/images:/images" \
  -v "$(pwd)/results:/results" \
  ultravision \
  /images \
  --model qwen/qwen3-vl-8b \
  --format jsonl \
  --out /results/outputs.jsonl \
  --api-base http://host.docker.internal:1234
```

Because LM Studio runs on the host, the container needs a way to reach `localhost:1234`. Use `--network host` on Linux (and keep `--api-base http://localhost:1234`), or add the host gateway alias when running on other platforms (`--add-host host.docker.internal:host-gateway`) and keep `--api-base http://host.docker.internal:1234`.

Start the web companion by passing `web` as the first argument. This tells the container to run `ultravision-web` and lets you expose ports as usual:

```bash
docker run --rm -it -p 8000:8000 \
  --add-host host.docker.internal:host-gateway \
  ultravision \
  web \
  --host 0.0.0.0 \
  --port 8000 \
  --api-base http://host.docker.internal:1234
```

The browser UI will be reachable at [http://localhost:8000](http://localhost:8000) and still points to the same LM Studio endpoint you provide via `--api-base / --api-key`.

## Documentation

- High-level overview, CLI details, web companion notes, and contributor workflow live under `docs/`:
  - `docs/overview.md`
  - `docs/cli.md`
  - `docs/web.md`
  - `docs/development.md`

## Development & docs

- Source layout: CLI (`ultravision/cli.py`), writers, API helpers, `images`, `util`, and the FastAPI server.
- Docstrings follow the Google style guide; keep docs in sync by updating the relevant `docs/*.md` files (`overview.md`, `cli.md`, `web.md`, `development.md`, etc.).
- Run `rg` to search across the repo and `pytest` to guard regressions; refer to `docs/development.md` for the project workflow.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

The suite covers image helpers, writer formats/resume behavior, CLI batching/dedup logic, and utility helpers like backoff/thread pools.

## License

MIT
