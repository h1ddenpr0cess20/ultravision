# UltraVision Overview

UltraVision is a fast, resilient batch image processor that pairs with LM Studio (or any OpenAI-compatible vision model) to generate concise descriptions of image sets. It exposes both a CLI for pipeline-style workloads and a browser-based UltraVision Studio for drag-and-drop interactions.

## Key Capabilities

- **Batch processing:** recursive scans, glob filters, per-request batching, resume/dedup, smart retries, and concurrency controls.
- **Multi-format outputs:** JSONL, JSON, plain text, Markdown, and CSV writers share a common extraction pipeline.
- **Image hygiene:** optional EXIF autorotate, resizing, and mime/hash metadata for reliable deduplication.
- **Auto-discovery:** probes localhost and LAN hosts for LM Studio/Ollama vision servers so the CLI and web UI can auto-fill `api_base`/`model` values and reuse a shared set of vision model hints.
- **Web companion:** a FastAPI-backed web interface that mirrors CLI settings and provides a rich drag-and-drop experience.
- **Extensible helpers:** shared utilities for API calls, data transformation, and concurrency allow consistent behavior across binaries and UIs.

## Architecture

1. **CLI runner (`ultravision.cli`):** Orchestrates argument parsing, file discovery, batching, retries, writer management, and logging with optional `rich` integration.
2. **Discovery (`ultravision.discovery`):** `VisionModelDiscovery` scans localhost, Docker gateways, and LAN ranges for LM Studio/Ollama `/v1/models`, filters for vision-compatible IDs, and surfaces local URLs for both CLI and web auto-configuration.
3. **Image helpers (`ultravision.images`):** Guess MIME types, read bytes, handle optional Pillow-based rotations/resizes, create metadata, and build LM Studio chat messages.
4. **Client writers (`ultravision.writer`):** Serialize outputs into the requested format and support resume awareness through JSONL introspection.
5. **API helpers (`ultravision.api`):** Send chat completions to LM Studio/OpenAI endpoints and normalize response text.
6. **Utilities (`ultravision.util`):** Backoff sleep and optional thread pool orchestration keep batches reliable and concurrent.
7. **Web server (`ultravision.web.server`):** FastAPI backend that accepts uploads, reuses helper modules, and proxies inference results to the browser.

## Dependencies and Environment

- **Core:** Python 3.11+, `requests`, `fastapi`, `uvicorn`, `rich` for CLI UX, and `Pillow` for EXIF and resizing (optional). Additional dependencies live in `pyproject.toml` and `requirements.txt`.
- **Optional tooling:** `uvicorn` for development server, `pytest` for tests, and `rich` for CLI formatting when available.

## Documentation Strategy

- All public-facing helpers are annotated with Google-style docstrings so IDEs and `pydoc` can describe behavior.
- This `docs/` folder centralizes usage, architecture, CLI options, web server instructions, and development expectations.
- Contributors should update both docstrings and `/docs` whenever features change to keep narrative and in-code documentation in sync.
