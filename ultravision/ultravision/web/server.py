"""FastAPI server powering the UltraVision web client."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..api import call_chat_completions, extract_text
from ..discovery import VisionModelDiscovery, DEFAULT_VISION_MODEL_HINTS
from ..images import file_meta, guess_mime, make_messages, to_data_url

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

app = FastAPI(
    title="UltraVision Studio",
    description="Browser companion for UltraVision with drag-and-drop uploads.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    """Return the compiled web client entry point.

    Returns:
        FileResponse: The UltraVision Studio HTML page.

    Raises:
        HTTPException: If the compiled frontend assets are missing.
    """
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=500, detail="Static assets missing; reinstall UltraVision.")
    return FileResponse(INDEX_FILE)


@app.post("/api/analyze")
async def analyze(
    files: List[UploadFile],
    api_base: str = Form("http://localhost:1234"),
    api_key: str = Form("lm-studio"),
    model: str = Form("qwen/qwen3-vl-8b"),
    system_prompt: str = Form("You are a precise, concise vision assistant."),
    prompt: str = Form("Describe the scene with crisp, confident detail."),
    temperature: float = Form(0.2),
    top_p: float = Form(1.0),
    presence_penalty: float = Form(0.0),
    frequency_penalty: float = Form(0.0),
    max_tokens: int = Form(1200),
    timeout: int = Form(120),
):
    """Accept uploads, build inference prompts, and forward the request to LM Studio.

    Args:
        files (List[UploadFile]): Uploaded image blobs (16-file limit).
        api_base (str): FastAPI form field with the LM Studio base URL.
        api_key (str): Bearer token for the LM Studio request.
        model (str): Model identifier (default ``qwen/qwen3-vl-8b``).
        system_prompt (str): System prompt guiding the assistant tone.
        prompt (str): User prompt appended to each image batch.
        temperature (float): Sampling temperature.
        top_p (float): Top-p sampling parameter.
        presence_penalty (float): Presence penalty for completions.
        frequency_penalty (float): Frequency penalty for completions.
        max_tokens (int): Token budget for completions.
        timeout (int): HTTP timeout in seconds.

    Returns:
        dict: Summary, raw response, asset metadata, and request parameters.

    Raises:
        HTTPException: When no images are uploaded, the batch is too large,
            or the backend inference call fails.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image.")
    if len(files) > 16:
        raise HTTPException(status_code=413, detail="Limit 16 images per request.")

    assets = []
    data_urls = []
    for upload in files:
        blob = await upload.read()
        if not blob:
            continue
        name = upload.filename or "upload"
        assets.append({"name": name, "meta": file_meta(name, blob)})
        data_urls.append(to_data_url(guess_mime(name), blob))

    if not data_urls:
        raise HTTPException(status_code=400, detail="No readable image data found.")

    messages = make_messages(system_prompt, prompt, data_urls)
    generation_params = {
        "top_p": float(top_p),
        "presence_penalty": float(presence_penalty),
        "frequency_penalty": float(frequency_penalty),
    }

    try:
        response = await run_in_threadpool(
            call_chat_completions,
            api_base,
            api_key,
            model,
            messages,
            float(temperature),
            int(max_tokens),
            int(timeout),
            generation_params,
        )
    except Exception as exc:  # pragma: no cover - network errors
        logger.exception("UltraVision inference failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    summary = extract_text(response).strip()
    return {
        "summary": summary,
        "raw": response,
        "assets": assets,
        "messages": messages,
        "request": {
            "api_base": api_base,
            "model": model,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "presence_penalty": float(presence_penalty),
            "frequency_penalty": float(frequency_penalty),
            "max_tokens": int(max_tokens),
            "timeout": int(timeout),
        },
    }


@app.get("/api/discover")
async def discover_servers(timeout: float = 2.0):
    """Return discovered LM Studio/Ollama servers and their vision models."""

    discovery = VisionModelDiscovery(
        timeout=float(timeout),
        additional_vision_models=list(DEFAULT_VISION_MODEL_HINTS),
    )
    try:
        return await discovery.discover()
    except Exception as exc:  # pragma: no cover - network failures
        logger.exception("Vision server discovery failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def run(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> None:
    """Start the FastAPI server for UltraVision Studio.

    Args:
        host (str): Host/IP to bind to.
        port (int): Port number for incoming connections.
        reload (bool): Whether to enable auto-reload for development.
    """
    import uvicorn

    uvicorn.run("ultravision.web.server:app", host=host, port=port, reload=reload)
