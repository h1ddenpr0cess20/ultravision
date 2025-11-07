# UltraVision Web Companion

The FastAPI-based web companion mirrors the CLI experience with a browsable drag-and-drop interface. It runs from `ultravision.web.server` and reuses the same helpers under the hood for metadata, messaging, and inference.

## Running the server

Ensure you have FastAPI/uvicorn installed and your LM Studio server running:

```bash
pip install .
uvicorn ultravision.web.server:app --reload
```

Then point your browser to [http://localhost:8000](http://localhost:8000). The static assets (React-like single-page app shipped under `ultravision/web/static`) handle the UI.

## Endpoints

### `GET /`
Serves the compiled UltraVision Studio frontend (`index.html`). The route raises `HTTP 500` if the static build is missing, so reinstalling the package or rerunning the frontend build will restore it.

### `POST /api/analyze`
Accepts multipart uploads and proxies them through LM Studio.

- **Fields:**
  - `files`: One or more `UploadFile` blobs (max 16 per request).
  - `api_base`, `api_key`, `model`: LM Studio connection details.
  - `system_prompt`, `prompt`: Guidance for the assistant.
  - `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`: Sampling knobs.
  - `max_tokens`, `timeout`: Limits for the completion call.

- **Behavior:**
  1. Reads blobs into memory, skipping empty uploads.
  2. Computes metadata (`file_meta`) and builds Base64 data URLs (`to_data_url`).
  3. Constructs chat messages via `make_messages` and delegates to `call_chat_completions` inside `run_in_threadpool` to avoid blocking the event loop.
  4. Returns a JSON payload containing `summary`, raw LM Studio `raw`, uploaded `assets`, `messages`, and `request` parameters.

- **Errors:**
  - `HTTP 400` when no files are provided or all uploads are empty.
  - `HTTP 413` when chunking more than 16 images.
  - `HTTP 502` when the backend inference throws an exception.

## Deployment notes

- The server adds CORS middleware that allows all origins for convenience; tighten it if embedding UltraVision in trusted environments.
- The static assets are served from `ultravision/web/static`. Rebuilding the frontend must place `index.html` and friends under this directory before shipping.
- Use `uvicorn --reload` during development so code changes automatically take effect.
