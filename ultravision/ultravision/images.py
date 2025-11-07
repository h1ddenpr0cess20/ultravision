"""Utilities for reading, transforming, and describing image assets."""

import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

try:
    from PIL import Image, ImageOps
    _PIL_OK = True
except Exception:
    _PIL_OK = False

PathLike = Union[str, Path]


def guess_mime(path: PathLike) -> str:
    """Guess the MIME type of a file based on its extension.

    Args:
        path (PathLike): File path or name to analyze.

    Returns:
        str: Guessed MIME type, defaulting to ``application/octet-stream``.
    """
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"

def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 digest for the provided bytes.

    Args:
        data (bytes): Raw file contents.

    Returns:
        str: Hex-encoded digest.
    """
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def load_image_bytes(path: Path) -> bytes:
    """Read a file as binary data.

    Args:
        path (Path): Filesystem path to open.

    Returns:
        bytes: File contents.
    """
    with open(path, "rb") as f:
        return f.read()

def autorotate_and_resize(path: Path, max_side: Optional[int]) -> Optional[bytes]:
    """Attempt to rotate the image via EXIF and shrink it to ``max_side``.

    Args:
        path (Path): Original image path for EXIF and MIME guessing.
        max_side (Optional[int]): Maximum width/height in pixels; ignored if ``None``.

    Returns:
        Optional[bytes]: Resized image contents, or ``None`` if Pillow is unavailable or fails.
    """
    if not _PIL_OK:
        return None
    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)
        if max_side and max(img.size) > max_side:
            ratio = max_side / float(max(img.size))
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        mime = guess_mime(path)
        fmt = "PNG"
        if mime in ("image/jpeg", "image/jpg"):
            fmt = "JPEG"
        elif mime == "image/webp":
            fmt = "WEBP"
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()
    except Exception:
        return None

def to_data_url(mime: str, data: bytes) -> str:
    """Encode bytes into a Base64 data URL for LM Studio uploads.

    Args:
        mime (str): MIME type for the provided bytes.
        data (bytes): File contents.

    Returns:
        str: ``data:{mime};base64,...`` URL.
    """
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"

def file_meta(path: PathLike, data: bytes) -> Dict[str, Any]:
    """Compose metadata for a given image payload.

    Args:
        path (PathLike): Original file path or name.
        data (bytes): Raw image bytes.

    Returns:
        Dict[str, Any]: Metadata including size, MIME, SHA-256, and optional dimensions.
    """
    meta: Dict[str, Any] = {
        "file": str(path),
        "size_bytes": len(data),
        "mime": guess_mime(path),
        "sha256": sha256_bytes(data),
    }
    if _PIL_OK:
        try:
            from io import BytesIO
            im = Image.open(BytesIO(data))
            meta["width"], meta["height"] = im.size
            meta["mode"] = im.mode
        except Exception:
            pass
    return meta

def find_images(root: Path, recursive: bool, patterns: Optional[List[str]]) -> List[Path]:
    """Discover image files under a root directory using glob patterns.

    Args:
        root (Path): Directory to scan.
        recursive (bool): Whether to walk subdirectories.
        patterns (Optional[List[str]]): Patterns to match, defaults to common image extensions.

    Returns:
        List[Path]: Sorted, unique file paths to process.
    """
    globs = patterns or ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp", "*.tiff"]
    paths = []
    if recursive:
        for pat in globs:
            paths.extend(root.rglob(pat))
    else:
        for pat in globs:
            paths.extend(root.glob(pat))
    uniq = sorted({p.resolve() for p in paths if p.is_file()})
    return uniq

def make_messages(system_prompt: str, user_prompt: str, image_data_urls: List[str]):
    """Build the chat content payload expected by LM Studio.

    Args:
        system_prompt (str): System-level instructions for the vision assistant.
        user_prompt (str): Optional textual prompt from the CLI/web UI.
        image_data_urls (List[str]): Base64-encoded URLs for each image blob.

    Returns:
        List[dict]: System and user messages arranged for ``/v1/chat/completions``.
    """
    content = []
    if user_prompt:
        content.append({"type": "text", "text": user_prompt})
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": content},
    ]
