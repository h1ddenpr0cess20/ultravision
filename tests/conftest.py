from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Tuple

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "ultravision"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))


@pytest.fixture
def image_factory(tmp_path) -> "ImageFactory":
    """Return helper that writes a PNG image at the requested path."""

    def _make(path: Path, size: Tuple[int, int] = (12, 8), color: Tuple[int, int, int] = (10, 200, 30)) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", size, color)
        img.save(path, format="PNG")
        return path

    return _make


ImageFactory = Callable[[Path, Tuple[int, int], Tuple[int, int, int]], Path]
