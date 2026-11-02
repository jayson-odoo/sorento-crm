"""QUOTE-SIGN-COLUMNS: the customer's sign page shows the quotation's own columns.

Owner, 2 Nov: the counter-sign link had no product photo column while the quotation did. The
page kept its own hand-written column list, so it drifted from the document the customer holds.
The rule pinned here: per scope, the sign page's column labels, in order, ARE the PDF's, because
both are read from one definition. And the pictures reach a customer with no login, as inline
bytes, never as a storage key or a link into a private bucket.

Postgres only, via ``blank_session``; the helpers are the PDF suite's own so both sides of the
comparison are built the same way.
"""
from __future__ import annotations

import json
import re

from ._pg_fixture import blank_session
from .test_project_quotation_pdf import (
    MARKER,
    PRICED_QTY,
    PRICED_RATE,
    _FakeBackend,
    _attachment,
    _issue,
    _photo_bytes,
    _product,
    _setup,
)


def _pdf_columns(html: str) -> list[list[str]]:
    """The header labels of every scope table in the rendered PDF, in order."""
    return [
        [re.sub(r"<[^>]+>", "", th) for th in re.findall(r"<th>(.*?)</th>", head)]
        for head in re.findall(r"<thead><tr>(.*?)</tr></thead>", html)
    ]


def _two_scope_issue(db, monkeypatch):
    """Scope A: one line with a photo and a drawing, one with neither. Scope B: no photo at all."""
    from app.models.projects import ProjectQuotationLine
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    env = _setup(db)
    owner = env["owner"]
    monkeypatch.setattr(
        images, "get_backend", lambda provider: _FakeBackend(_photo_bytes(320, 320))
    )
    with_photo = _product(db, env["category"].id, env["uom"], description=f"{MARKER} WC suite")
    plain = _product(db, env["category"].id, env["uom"], description=f"{MARKER} bottle trap")
    photo = _attachment(db, env["company_id"], "wc.png")
    drawing = _attachment(db, env["company_id"], "wc-drawing.png")

    document = qdocs.create_document(db, project=env["project"], actor_user_id=owner)
    a = qdocs.add_scope(db, document=document, scope_label=f"{MARKER} A", actor_user_id=owner)
    b = qdocs.add_scope(db, document=document, scope_label=f"{MARKER} B", actor_user_id=owner)
    va = quotes.current_version(db, a.id)
    first = quotes.upsert_line(
        db,
        version=va,
        actor_user_id=owner,
        payload={"product_id": with_photo.id, "unit_price": PRICED_RATE, "quantity": PRICED_QTY},
    )
    quotes.upsert_line(
        db,
        version=va,
        actor_user_id=owner,
        payload={"product_id": plain.id, "unit_price": "6.50", "quantity": 2},
    )
    quotes.upsert_line(
        db,
        version=quotes.current_version(db, b.id),
        actor_user_id=owner,
        payload={"product_id": plain.id, "unit_price": "6.50", "quantity": 3},
    )
    # Stamped directly: the picks validation is the grid's concern, not this lane's.
    line = db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == first.id).one()
    line.image_attachment_id = photo.id
    line.drawing_attachment_id = drawing.id
    db.flush()
    return _issue(db, document, owner)


def test_the_sign_page_columns_are_the_pdf_columns_scope_by_scope(monkeypatch):
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_pdf_service as qpdf

    with blank_session() as db:
        issued = _two_scope_issue(db, monkeypatch)

        pdf = _pdf_columns(qpdf.build_issue_html(db, issued))
        page = qdocs.serialize_sign_page(db, issued)
        sign = [[c["label"] for c in scope["columns"]] for scope in page["scopes"]]

        assert sign == pdf
        # The photo column is there for the scope with a photo, and only for it.
        assert "PRODUCT IMAGE" in sign[0]
        assert "PRODUCT IMAGE" not in sign[1]


def test_the_sign_page_line_carries_its_photo_and_drawing_as_inline_bytes(monkeypatch):
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        issued = _two_scope_issue(db, monkeypatch)

        page = qdocs.serialize_sign_page(db, issued)
        with_photo, without = page["scopes"][0]["lines"]

        assert with_photo["image_url"].startswith("data:image/jpeg;base64,")
        assert with_photo["drawing_url"].startswith("data:image/jpeg;base64,")
        assert without["image_url"] is None
        assert without["drawing_url"] is None


def test_the_public_page_answers_columns_and_photos_to_an_anonymous_customer(monkeypatch):
    """Over HTTP, with no credential: `response_model` drops undeclared fields silently, so the
    wire is what is asserted. Nothing in it names a storage key or a bucket host."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        issued = _two_scope_issue(db, monkeypatch)
        token = qdocs.issue_sign_link(db, record=issued)
        db.commit()

        app.dependency_overrides[get_db] = lambda: db
        try:
            response = TestClient(app).get(f"/api/v1/public/quotation-sign/{token}")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200, response.text
        body = response.json()
        labels = [c["label"] for c in body["scopes"][0]["columns"]]
        assert labels[:3] == ["ITEM", "PRODUCT IMAGE", "TECHNICAL SPEC"]
        assert [c["key"] for c in body["scopes"][0]["columns"]][:3] == ["item", "image", "spec"]
        assert body["scopes"][0]["lines"][0]["image_url"].startswith("data:image/jpeg;base64,")

        wire = json.dumps(body)
        for leak in ("cdn.zzt.test", f"products/{MARKER}", "image_attachment_id", "file_path"):
            assert leak not in wire


def test_a_second_page_load_does_not_download_the_pictures_again(monkeypatch):
    """The page is public and refetched after every answer: the pictures are rendered once per
    attachment, not once per request (security review S1)."""
    from app.services import product_image_service as images
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        issued = _two_scope_issue(db, monkeypatch)
        backend = _FakeBackend(_photo_bytes(320, 320))
        monkeypatch.setattr(images, "get_backend", lambda provider: backend)

        first = qdocs.serialize_sign_page(db, issued)
        downloads = len(backend.keys)
        second = qdocs.serialize_sign_page(db, issued)

        assert downloads == 2  # the photo and the drawing
        assert len(backend.keys) == downloads
        assert second["scopes"][0]["lines"][0]["image_url"] == first["scopes"][0]["lines"][0]["image_url"]
