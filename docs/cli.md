# UltraVision CLI Reference

The CLI (`ultravision`) is the most direct way to process large image sets with LM Studio or any OpenAI-compatible vision model. It focuses on repeatable batch runs, deterministic outputs, and resilience to transient API failures.

## Launching a run

Install the package and invoke the CLI from the directory containing your images:

```bash
pip install .
ultravision ./images --model qwen/qwen3-vl-8b --format jsonl --out results.jsonl
```

Every run:

1. Globs the given directory (`images` in the example) for common formats.
2. Applies optional autorotate/resize filters per image.
3. Groups files into batches (`--per-request N`).
4. Sends each batch to the LM Studio `/v1/chat/completions` endpoint.
5. Writes the generated text plus metadata via the format-specific `Writer` implementation.

## Important CLI flags

| Flag | Description |
| --- | --- |
| `--model` | LM Studio-compatible model ID (default `qwen/qwen3-vl-8b`). |
| `--api-base` | Base URL for your LM Studio instance (e.g., `http://localhost:1234`). |
| `--api-key` | Bearer token header (LM Studio ignores the actual value). |
| `--auto-discover` | Scan for LM Studio/Ollama hosts and auto-select the first vision-ready model. |
| `--prefer-service` | When auto-discovering, prefer `lm_studio` (default) or `ollama`. |
| `--lm-studio-port` / `--ollama-port` | Ports probed during auto-discovery (defaults 1234 / 11434). |
| `--discovery-timeout` / `--discovery-models` | Tune the HTTP timeout and add extra model substrings to treat as “vision”. |
| `--prompt` / `--system-prompt` | Customize the user/system messages sent before images. |
| `--per-request` | Number of images per inference call; helps balance latency and JSON payload size. |
| `--recursive` / `--patterns` | Traverse subdirectories and match custom glob patterns. |
| `--limit` | Stop after a set number of images (useful for sampling). |
| `--resume` | With `jsonl` output, avoids reprocessing images whose SHA-256 hashes already exist in the output. |
| `--format` | Output format: `jsonl`, `json`, `text`, `markdown`, or `csv`. |
| `--out` | Destination file; defaults to `outputs.<format>`. |
| `--fail-log` | Path to write failing batch metadata for offline inspection. |
| `--concurrency` | Number of concurrent API requests (default 2). |
| `--autorotate` / `--max-side` | Pillow-powered EXIF autorotation and resizing. |
| `--max-tokens`, `--temperature`, `--timeout`, `--retries` | Control LM Studio generation and retry behavior. |
| `--extra` | JSON dictionary merged into the chat completions payload (e.g., `{"top_p":0.9}`). |

### Auto-discovery

Pass `--auto-discover` when you don’t want to type `--api-base`/`--model`. UltraVision will instantiate the bundled `VisionModelDiscovery`, scan localhost plus LAN ranges for LM Studio/Ollama servers, and pick the first vision-capable model. Use `--prefer-service ollama` if you’d like Ollama options ranked first, override the probe ports with `--lm-studio-port` / `--ollama-port`, and add extra model substrings (e.g., `gemma3`) via `--discovery-models`. If no servers are reachable the CLI exits early so you can provide manual values instead.

### Resume and deduplication

- The `Writer` already helps deduplicate inside each run by hashing every image and skipping duplicates via the shared hashing helpers (`images.sha256_bytes`).
- When `--resume` and `--format jsonl` are used together, the writer scans the existing JSONL file for stored hashes and skips any collisions.
- `--limit` still respects resume/dedup filters to avoid reprocessing already-processed images.

### Output formats

- `jsonl` (default): One record per batch with metadata (`files`, `meta`, `text`, `raw`). Great for resumed runs and rehydrating data.
- `json`: Aggregates every record into a JSON array; written at context exit to keep the whole structure valid.
- `text` / `markdown`: Human-readable narratives with per-batch headings and separators.
- `csv`: Flattens the first metadata entry (typically the first file) plus the aggregated text for spreadsheets or data ingestion pipelines.

All writers rely on `api.extract_text` to pull the assistant message out of LM Studio responses.

### Logging and failures

- `rich` is optional; if available, it powers spinner/status updates and colored logging via the `info`, `warn`, and `err` helpers.
- Failed batches (after exhausting retries) are logged to `failures.log` (or the provided `--fail-log`) in JSONL format for replay.

## Tips for reproducibility

1. Pin your LM Studio server, model, and prompts in a single script.
2. Keep the `--resume`/`--fail-log` artifacts if sharing runs with teammates.
3. Use `--extra` when experimenting with sampling knobs beyond `--temperature` and `--max-tokens`.
