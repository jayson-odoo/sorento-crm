"""Unit tests for complaint-PDF photo classification (`_image_mime`).

The bug this guards: WhatsApp `.jpeg` uploads land with a NULL or generic
(`application/octet-stream`) mime_type, so a mime-only check dropped them out of
the PHOTOS section into OTHER ATTACHMENTS. `_image_mime` adds an extension
fallback. Pure function — no DB / WeasyPrint needed.
"""
from types import SimpleNamespace

from app.services.complaint_pdf_service import _image_mime


def _att(mime=None, name=None, path=None):
    return SimpleNamespace(mime_type=mime, original_filename=name, file_path=path)


def test_trusts_explicit_image_mime():
    assert _image_mime(_att(mime="image/png", name="x.bin")) == "image/png"


def test_jpeg_with_null_mime_inferred_from_filename():
    att = _att(mime=None, name="WhatsApp Image 1 (cistern).jpeg")
    assert _image_mime(att) == "image/jpeg"


def test_jpeg_with_octet_stream_mime_inferred_from_filename():
    att = _att(mime="application/octet-stream", name="photo.JPG")
    # case-insensitive extension match -> still an image
    assert _image_mime(att) == "image/jpeg"


def test_falls_back_to_file_path_when_no_original_filename():
    att = _att(mime="", name=None, path="uploads/abc/cracked.png")
    assert _image_mime(att) == "image/png"


def test_non_image_extension_returns_none():
    assert _image_mime(_att(mime=None, name="invoice.pdf")) is None
    assert _image_mime(_att(mime="application/pdf", name="invoice.pdf")) is None


def test_no_name_no_mime_returns_none():
    assert _image_mime(_att()) is None


def test_heic_supported():
    assert _image_mime(_att(mime=None, name="IMG_2026.heic")) == "image/heic"
