import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    from PIL import Image, ImageOps
    _PIL_OK = True
except Exception:
    _PIL_OK = False

def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"

def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()

def load_image_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def autorotate_and_resize(path: Path, max_side: Optional[int]) -> Optional[bytes]:
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
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"

def file_meta(path: Path, data: bytes) -> Dict[str, Any]:
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
    content = []
    if user_prompt:
        content.append({"type": "text", "text": user_prompt})
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": content},
    ]
