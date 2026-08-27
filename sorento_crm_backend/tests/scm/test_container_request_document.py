"""R23 - the request as a file, on demand, without telling the supplier anything.

`POST /api/v1/scm/container-requests/document?format=xlsx|pdf` renders the lines currently on
Ms Tee's screen. It is the gear menu's "Download XLSX" / "Download PDF", and the whole point
is what it does NOT do: no notice row, no token, no email, nothing the supplier has been told.
A send is a decision; reading the sheet is not.

The two properties worth pinning: the bytes come from the SAME builders the send uses (a
download that could disagree with the emailed sheet is not worth having), and the read
permission is what guards it, since nothing is created.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.models.supplier_notice import SupplierNotice
from app.services.scm import supplier_notice_service
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

URL = "/api/v1/scm/container-requests/document"


@pytest.fixture(autouse=True)
def _no_pdf(monkeypatch):
    """WeasyPrint is a deployment fact, not a property of this code - same stub as S8's suite."""
    monkeypatch.setattr(
        supplier_notice_service, "render_document", lambda html: b"%PDF-1.4 stub"
    )


def _body(w: World, qty: float = 42) -> dict:
    return {
        "supplier_id": str(w.supplier.id),
        "lines": [{"product_id": str(w.product("A").id), "qty": qty}],
    }


def _rows(data: bytes) -> list[tuple]:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(data), data_only=True)
    return [tuple(r) for r in wb.active.iter_rows(values_only=True)]


def test_the_xlsx_opens_and_carries_the_lines_on_screen(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock("A", packed=120, unfinished=340)

    r = TestClient(app).post(f"{URL}?format=xlsx", json=_body(w, 500))

    assert r.status_code == 200, r.text
    rows = _rows(r.content)
    flat = [str(cell) for row in rows for cell in row if cell is not None]
    assert w.product("A").product_code in flat
    assert "500" in flat or 500 in [cell for row in rows for cell in row]


def test_the_xlsx_is_named_for_the_supplier_and_the_day(scm_app):
    # AC-C9: `container-request-<supplier code>-<yyyymmdd>.xlsx`, through the RFC-5987 helper
    # so a Chinese supplier code cannot 500 the download on a latin-1 header.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(f"{URL}?format=xlsx", json=_body(w))

    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment; ")
    assert f"container-request-{w.supplier.supplier_code}-" in disposition
    assert ".xlsx" in disposition
    assert "filename*=UTF-8''" in disposition


def test_the_pdf_is_a_pdf(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(f"{URL}?format=pdf", json=_body(w))

    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")
    assert r.headers["content-type"] == "application/pdf"
    assert ".pdf" in r.headers["content-disposition"]


def test_the_format_defaults_to_the_sheet(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(URL, json=_body(w))

    assert r.status_code == 200, r.text
    assert ".xlsx" in r.headers["content-disposition"]


def test_downloading_tells_the_supplier_nothing(scm_app):
    # The whole reason this route exists rather than a send: a document she can read without
    # a factory receiving an ask she has not finished editing.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    TestClient(app).post(f"{URL}?format=xlsx", json=_body(w))
    TestClient(app).post(f"{URL}?format=pdf", json=_body(w))

    assert (
        db.query(SupplierNotice)
        .filter(SupplierNotice.supplier_id == str(w.supplier.id))
        .count()
        == 0
    )


def test_an_unknown_format_is_refused(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(f"{URL}?format=exe", json=_body(w))

    assert r.status_code == 422, r.text


def test_a_product_that_is_not_ours_is_a_422_not_a_500(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)

    r = TestClient(app).post(
        f"{URL}?format=xlsx",
        json={
            "supplier_id": str(w.supplier.id),
            "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
    )

    assert r.status_code == 422, r.text


def test_the_document_requires_the_read_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(
        f"{URL}?format=xlsx",
        json={
            "supplier_id": str(uuid.uuid4()),
            "lines": [{"product_id": str(uuid.uuid4()), "qty": 1}],
        },
    )

    assert r.status_code == 403, r.text
