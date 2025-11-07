from __future__ import annotations

import base64
from io import BytesIO

import pytest

from ultravision import images


def test_guess_mime_falls_back_to_octet_stream(tmp_path):
    unknown = tmp_path / "sample.unknownext"
    unknown.write_bytes(b"data")
    assert images.guess_mime(unknown) == "application/octet-stream"


def test_sha256_bytes_is_deterministic():
    data = b"ultravision"
    assert images.sha256_bytes(data) == images.sha256_bytes(data)
    assert images.sha256_bytes(data) != images.sha256_bytes(b"other")


def test_to_data_url_round_trip(tmp_path, image_factory):
    img_path = image_factory(tmp_path / "pic.png")
    payload = img_path.read_bytes()
    mime = images.guess_mime(img_path)
    data_url = images.to_data_url(mime, payload)
    assert data_url.startswith(f"data:{mime};base64,")
    decoded = base64.b64decode(data_url.split(",", 1)[1])
    assert decoded == payload


@pytest.mark.skipif(not images._PIL_OK, reason="Pillow is required for this test")
def test_file_meta_includes_dimensions(tmp_path, image_factory):
    img_path = image_factory(tmp_path / "sized.png", size=(24, 10))
    data = img_path.read_bytes()
    meta = images.file_meta(img_path, data)
    assert meta["width"] == 24
    assert meta["height"] == 10
    assert meta["mime"] == "image/png"
    assert meta["size_bytes"] == len(data)


@pytest.mark.skipif(not images._PIL_OK, reason="Pillow is required for this test")
def test_autorotate_and_resize_resizes_when_needed(tmp_path, image_factory):
    img_path = image_factory(tmp_path / "big.png", size=(120, 60))
    resized = images.autorotate_and_resize(img_path, max_side=20)
    assert resized is not None
    from PIL import Image

    with Image.open(BytesIO(resized)) as im:
        assert max(im.size) == 20


def test_find_images_handles_patterns_and_recursion(tmp_path, image_factory):
    root = tmp_path / "root"
    nested = root / "nested"
    img1 = image_factory(root / "one.png")
    img2 = nested / "two.jpg"
    img2.parent.mkdir(parents=True, exist_ok=True)
    img2.write_bytes(img1.read_bytes())
    extra = image_factory(root / "ignore.gif")

    found = images.find_images(root, recursive=False, patterns=["*.png", "*.jpg"])
    assert found == [img1.resolve()]

    found_recursive = images.find_images(root, recursive=True, patterns=["*.png", "*.jpg"])
    assert sorted(found_recursive) == sorted({img1.resolve(), img2.resolve()})
    assert extra.resolve() not in found_recursive


def test_make_messages_includes_prompts_and_urls():
    urls = ["data:image/png;base64,AAA", "data:image/jpeg;base64,BBB"]
    messages = images.make_messages("system prompt", "describe", urls)
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "system prompt"
    assert messages[1]["role"] == "user"
    assert any(part["type"] == "text" for part in messages[1]["content"])
    image_parts = [part for part in messages[1]["content"] if part["type"] == "image_url"]
    assert [part["image_url"]["url"] for part in image_parts] == urls
