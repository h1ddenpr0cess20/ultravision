# ultravision

Ultra-fast, resilient batch image processor for **LM Studio** using **Qwen/Qwen3-VL** (or any OpenAI-compatible vision model).

**Features**

- Recursive folder scan, glob patterns, `--limit`
- **Resume** mode (skips already-processed images via SHA-256)
- **Concurrency** with smart retry/backoff
- Optional **EXIF autorotate** and **resize** (Pillow)
- Output to **jsonl / json / text / csv / markdown**
- Deduplicate by content hash
- Live spinner and colored logs via **rich**
- Data URLs with base64 for LM Studio `/v1/chat/completions`

## Install

```bash
pip install .
# or
pip install ultravision-0.1.0-py3-none-any.whl  # if you built a wheel
```

## Quick Start

Start LM Studio server at `http://localhost:1234` and load `qwen/qwen3-vl-8b`.

```bash
ultravision ./images   --model qwen/qwen3-vl-8b   --format jsonl   --out results.jsonl
```

Parallel, with autorotate/resize and 2 images per request:

```bash
ultravision ./images   --per-request 2 --concurrency 4   --autorotate --max-side 1600
```

Resume & write markdown:

```bash
ultravision ./images --resume --format markdown --out run.md
```

If you omit `--out`, the tool saves to `outputs.<format>` automatically (for example `outputs.csv`).

CSV for spreadsheets:

```bash
ultravision ./images --format csv --out out.csv
```

## CLI

Run `ultravision --help` for full options.

## Web Studio

Launch the browser companion with a single command:

```bash
pip install .
uvicorn ultravision.web.server:app --reload
```

Then open [http://localhost:8000](http://localhost:8000) to access UltraVision Studio, drag in imagery, and point the settings panel at your LM Studio (or any OpenAI-compatible) endpoint.

## Testing

Install the development dependencies and run the Pytest suite from the project root:

```bash
pip install -e ".[dev]"
pytest
```

The tests cover the image helpers, writer formats/resume behavior, CLI batching/deduplication logic, and utility helpers to guard against regressions.

## License

MIT
