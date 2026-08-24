"""PromotionsPdfService.render_pdf tests (app/services/promotions_pdf_service.py).

Uses REAL committed fixture bytes (a small 2-page PDF + a PNG) injected via a
monkeypatched storage backend (no S3/R2 network). Verifies:
 - merge preserves the caller's promotion_ids order and per-promo sort_order;
 - a non-printable attachment (.txt) is skipped and reported;
 - zero printable attachments -> ValueError.
"""
from __future__ import annotations

import os
import uuid

import fitz  # PyMuPDF
import pytest

from app.models.marketing import Promotion, PromotionAttachment
from app.models.resources import Attachment, AttachmentDirectory, AttachmentType
from app.services import promotions_pdf_service as pdf_mod
from app.services.promotions_pdf_service import PromotionsPdfService
from tests._pg_fixture import blank_session

_FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")
PDF_BYTES = open(os.path.join(_FIXDIR, "sample_flyer.pdf"), "rb").read()
PNG_BYTES = open(os.path.join(_FIXDIR, "sample_flyer.png"), "rb").read()
TXT_BYTES = open(os.path.join(_FIXDIR, "notes.txt"), "rb").read()

# The 2-page fixture PDF -> 2 pages; the image -> 1 page.
_PDF_PAGE_COUNT = 2


class _FakeBackend:
    """Returns fixture bytes keyed by the storage key (== attachment.file_path)."""

    def __init__(self, store):
        self._store = store

    def download_file(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]


@pytest.fixture
def db(monkeypatch):
    with blank_session() as s:
        # Inject the fixture bytes via a fake storage backend keyed by file_path.
        store: dict[str, bytes] = {}
        monkeypatch.setattr(pdf_mod, "get_backend", lambda provider: _FakeBackend(store))
        s._fixture_store = store  # type: ignore[attr-defined]
        yield s


def _mk_promo(db) -> Promotion:
    p = Promotion(
        id=str(uuid.uuid4()),
        description=f"Promo {uuid.uuid4().hex[:6]}",
        access_levels=["dealer"],
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _mk_attachment(db, *, key: str, raw: bytes, mime: str, filename: str) -> Attachment:
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=filename,
        stored_filename=filename,
        file_path=key,
        file_size_bytes=len(raw),
        mime_type=mime,
        access_levels=["dealer"],
        storage_provider="s3",
    )
    db.add(att)
    db.flush()
    db._fixture_store[key] = raw  # type: ignore[attr-defined]
    return att


def _link(db, promo, att, *, sort_order):
    db.add(
        PromotionAttachment(
            id=str(uuid.uuid4()),
            promotion_id=promo.id,
            attachment_id=att.id,
            sort_order=sort_order,
        )
    )
    db.flush()


def test_merge_preserves_promotion_order_and_sort_order(db):
    # Promo A: image (sort 0) then pdf (sort 1). Promo B: single pdf.
    promo_a = _mk_promo(db)
    promo_b = _mk_promo(db)
    img = _mk_attachment(db, key="a/img.png", raw=PNG_BYTES, mime="image/png", filename="img.png")
    pdf_a = _mk_attachment(db, key="a/flyer.pdf", raw=PDF_BYTES, mime="application/pdf", filename="flyer.pdf")
    pdf_b = _mk_attachment(db, key="b/flyer.pdf", raw=PDF_BYTES, mime="application/pdf", filename="flyerb.pdf")
    _link(db, promo_a, img, sort_order=0)
    _link(db, promo_a, pdf_a, sort_order=1)
    _link(db, promo_b, pdf_b, sort_order=0)
    db.commit()

    # Order B then A at the caller (grid) level.
    pdf_bytes, filename, skipped = PromotionsPdfService(db).render_pdf([promo_b.id, promo_a.id])

    assert skipped == []
    assert filename.startswith("promotions-expiring-") and filename.endswith(".pdf")
    # Total pages = B(2) + A image(1) + A pdf(2) = 5.
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        assert doc.page_count == _PDF_PAGE_COUNT + 1 + _PDF_PAGE_COUNT


def test_within_promo_sort_order_orders_attachments(db):
    promo = _mk_promo(db)
    # Give the image a LOWER sort_order so it comes first; pdf second.
    img = _mk_attachment(db, key="img2.png", raw=PNG_BYTES, mime="image/png", filename="img2.png")
    pdf = _mk_attachment(db, key="flyer2.pdf", raw=PDF_BYTES, mime="application/pdf", filename="flyer2.pdf")
    _link(db, promo, pdf, sort_order=5)
    _link(db, promo, img, sort_order=1)
    db.commit()

    pdf_bytes, _fn, skipped = PromotionsPdfService(db).render_pdf([promo.id])
    assert skipped == []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        # image (1 page) first, then the 2-page pdf -> first page is the small
        # square image page (width == height == 100 for the fixture PNG).
        assert doc.page_count == 1 + _PDF_PAGE_COUNT
        first = doc[0].rect
        assert round(first.width) == round(first.height)  # square image page


def test_non_printable_attachment_skipped_and_reported(db):
    promo = _mk_promo(db)
    pdf = _mk_attachment(db, key="ok.pdf", raw=PDF_BYTES, mime="application/pdf", filename="ok.pdf")
    txt = _mk_attachment(db, key="notes.txt", raw=TXT_BYTES, mime="text/plain", filename="notes.txt")
    _link(db, promo, pdf, sort_order=0)
    _link(db, promo, txt, sort_order=1)
    db.commit()

    pdf_bytes, _fn, skipped = PromotionsPdfService(db).render_pdf([promo.id])
    assert "notes.txt" in skipped
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        assert doc.page_count == _PDF_PAGE_COUNT  # only the printable pdf


def test_zero_printable_raises(db):
    promo = _mk_promo(db)
    txt = _mk_attachment(db, key="only.txt", raw=TXT_BYTES, mime="text/plain", filename="only.txt")
    _link(db, promo, txt, sort_order=0)
    db.commit()

    with pytest.raises(ValueError):
        PromotionsPdfService(db).render_pdf([promo.id])


def test_unreadable_download_skipped(db):
    # An attachment whose bytes aren't in the store -> download raises -> skipped.
    promo = _mk_promo(db)
    good = _mk_attachment(db, key="good.pdf", raw=PDF_BYTES, mime="application/pdf", filename="good.pdf")
    bad = Attachment(
        id=str(uuid.uuid4()),
        original_filename="missing.pdf",
        stored_filename="missing.pdf",
        file_path="missing.pdf",  # not in the fixture store -> download FileNotFound
        file_size_bytes=1,
        mime_type="application/pdf",
        access_levels=["dealer"],
        storage_provider="s3",
    )
    db.add(bad)
    db.flush()
    _link(db, promo, good, sort_order=0)
    _link(db, promo, bad, sort_order=1)
    db.commit()

    pdf_bytes, _fn, skipped = PromotionsPdfService(db).render_pdf([promo.id])
    assert "missing.pdf" in skipped
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        assert doc.page_count == _PDF_PAGE_COUNT
