"""Unit tests for grid thumbnail generation (image_thumbnailer).

Guards the Files-grid perf fix: full-resolution product photos (up to ~4500px)
must be downscaled to a small JPEG so the grid paints a tiny image instead of a
20-MP bitmap. Pure function - no DB / storage needed.
See docs/plans/PLAN-attachment-grid-thumbnails.md.
"""
import io

from PIL import Image

from app.services.image_thumbnailer import (
    _MAX_EDGE,
    generate_thumbnail,
    thumbnail_key_for,
)


def _jpeg(w: int, h: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), (200, 50, 50) if mode == "RGB" else 0).save(buf, "JPEG")
    return buf.getvalue()


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (0, 0, 0, 255)).save(buf, "PNG")
    return buf.getvalue()


def test_downscales_large_image_within_max_edge():
    thumb = generate_thumbnail(_jpeg(4500, 4500), "image/jpeg")
    assert thumb is not None
    im = Image.open(io.BytesIO(thumb))
    assert max(im.size) <= _MAX_EDGE
    assert im.format == "JPEG"
    assert im.mode == "RGB"


def test_shrinks_byte_size_dramatically():
    original = _jpeg(4500, 4500)
    thumb = generate_thumbnail(original, "image/jpeg")
    assert thumb is not None
    # A 20-MP photo must collapse to a tiny thumbnail.
    assert len(thumb) < len(original) / 10


def test_preserves_aspect_ratio():
    thumb = generate_thumbnail(_png(4000, 1000), "image/png")
    assert thumb is not None
    w, h = Image.open(io.BytesIO(thumb)).size
    assert w == _MAX_EDGE  # long edge clamped
    assert h == _MAX_EDGE // 4  # 4:1 aspect kept


def test_converts_non_rgb_modes_to_rgb():
    # CMYK / palette / alpha must flatten to a valid RGB JPEG (WhatsApp-safe).
    buf = io.BytesIO()
    Image.new("CMYK", (2000, 2000)).save(buf, "JPEG")
    thumb = generate_thumbnail(buf.getvalue(), "image/jpeg")
    assert thumb is not None
    assert Image.open(io.BytesIO(thumb)).mode == "RGB"


def test_returns_none_for_non_image_mime():
    assert generate_thumbnail(b"%PDF-1.7 not an image", "application/pdf") is None


def test_returns_none_for_corrupt_image_bytes():
    assert generate_thumbnail(b"\xff\xd8\xff\xe0garbage", "image/jpeg") is None


def test_returns_none_for_empty_content():
    assert generate_thumbnail(b"", "image/jpeg") is None


def test_thumbnail_key_is_deterministic_suffix():
    assert thumbnail_key_for("general/uuid/pic.jpg") == "general/uuid/pic.jpg.thumb.jpg"
