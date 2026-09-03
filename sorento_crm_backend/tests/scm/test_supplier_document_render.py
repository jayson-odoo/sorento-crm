"""S4 - the PDF draws the SAME sheet the xlsx does (R12, AC-D4, AC-D7).

The three renderers used to be three shapes, so "the link view, the PDF and the xlsx tally
100%" was not a property anybody could check. It is now one object: the send path builds a
`SheetModel` once and hands that instance to both renderers, which is asserted here by
identity - a copy would be free to drift on the next change.

WeasyPrint and the object store are stubbed the same way S8's own suite stubs them: this file
is about what the HTML says, not about a native library.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services.scm import container_request_xlsx
from app.services.scm import supplier_document_model as model
from app.services.scm import supplier_notice_service as svc
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import require_aliases
from tests.scm.conftest import requires_pg
from tests.scm.test_loading_plan import World

pytestmark = requires_pg

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "documentation"
    / "plans"
    / "scm"
    / "fixtures"
    / "jinbaichuan-stock-list-2026-07-27.xlsx"
)

SUPPLIER = {"supplier_code": "JBC", "supplier_name": "JINBAICHUAN"}


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    monkeypatch.setattr(svc, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(svc, "_store", lambda data, filename: ("s3", f"exports/t/{filename}"))


def _sheet(db, monkeypatch, lines: list[dict] | None = None):
    monkeypatch.setattr(model, "_retained_stock_list", lambda _db, _sid, **_kw: FIXTURE.read_bytes())
    return model.build(
        db,
        supplier_id=str(uuid.uuid4()),
        lines=lines or [{"item_code": "SRTSP131", "product_name": "Plane", "qty": 12}],
    )


def _html(db, monkeypatch, **kwargs) -> str:
    return svc._document_html(
        supplier=SUPPLIER,
        plan=None,
        pack=[],
        produce=[],
        notice_type="container_request",
        sheet=_sheet(db, monkeypatch, **kwargs),
    )


# --------------------------------------------------------------------------- #
# the PDF
# --------------------------------------------------------------------------- #


def test_the_pdf_prints_their_columns_and_ours(monkeypatch):
    # AC-D4. Their ten headings, in their words, plus column K. The six columns of our own
    # naming that the PDF used to carry are gone.
    with pg_session() as db:
        require_aliases(db, "supplier_inventory")
        html = _html(db, monkeypatch)

        for label in ("序号", "型号", "商标", "规格", "品名", "包装好库存", "空瓷", "备注"):
            assert label in html, label
        assert model.QTY_TO_LOAD_LABEL_ZH in html
        assert model.QTY_TO_LOAD_LABEL_EN in html
        assert "金百川库存表 2026年7月27日" in html


def test_the_pdf_merges_a_family_the_way_their_sheet_does(monkeypatch):
    # AC-D4. `A3:A11` is nine rows under one 序号 and one volume; nine copies of the volume
    # would read as nine times the volume.
    with pg_session() as db:
        require_aliases(db, "supplier_inventory")
        html = _html(db, monkeypatch)

        assert 'rowspan="9"' in html
        assert "合计" in html
        assert "page-break-inside" in html
        assert "<thead>" in html  # the header repeats on every page
        assert "landscape" in html


def test_the_pdf_keeps_their_marks_and_our_bilingual_intro(monkeypatch):
    with pg_session() as db:
        require_aliases(db, "supplier_inventory")
        html = _html(db, monkeypatch)

        assert "fill" in html and "#FFFF00".lower() in html.lower()
        assert "请为下一个货柜准备以下项目" in html
        assert "宋体" in html


def test_a_request_with_no_sheet_behind_it_still_draws(monkeypatch):
    # AC-H2. A notice minted before S4 has no model to draw, and its PDF must still render
    # the ask rather than an empty page.
    with pg_session() as db:
        require_aliases(db, "supplier_inventory")
        html = svc._document_html(
            supplier=SUPPLIER,
            plan=None,
            pack=[{"item_code": "A", "product_name": "Basin", "qty": 4}],
            produce=[],
            notice_type="container_request",
        )

        assert "Container Request / 配柜要求" in html
        assert "Item / 型号" in html


# --------------------------------------------------------------------------- #
# one model, two renderers
# --------------------------------------------------------------------------- #


def test_the_send_builds_the_sheet_once_and_hands_it_to_both(scm_app, monkeypatch):
    # AC-D7. Identity, not equality: two models built independently would be free to drift
    # apart on the next change, and "the PDF and the xlsx tally" would stop being a property.
    app, db, *_ = scm_app
    require_aliases(db, "supplier_inventory")
    w = World(db)
    w.stock("A", packed=120, unfinished=340)

    seen: dict[str, object] = {}
    real_html = svc._document_html
    real_render = container_request_xlsx.render

    def spy_html(**kwargs):
        seen["pdf"] = kwargs.get("sheet")
        return real_html(**kwargs)

    def spy_render(sheet):
        seen["xlsx"] = sheet
        return real_render(sheet)

    monkeypatch.setattr(svc, "_document_html", spy_html)
    monkeypatch.setattr(container_request_xlsx, "render", spy_render)

    svc.request_and_notify(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": 500}],
        # A send names at least one recipient since R9 (AC-C2).
        recipients=["sheet-once@example.test"],
    )

    assert isinstance(seen.get("pdf"), model.SheetModel)
    assert seen["pdf"] is seen["xlsx"]


def test_the_download_builds_the_sheet_once_too(scm_app, monkeypatch):
    # The gear menu's Download PDF / Download XLSX runs the same builder, so a downloaded
    # sheet cannot disagree with the emailed one.
    app, db, *_ = scm_app
    require_aliases(db, "supplier_inventory")
    w = World(db)

    seen: list[object] = []
    real_render = container_request_xlsx.render
    monkeypatch.setattr(
        container_request_xlsx,
        "render",
        lambda sheet: (seen.append(sheet), real_render(sheet))[1],
    )

    data, name = svc.request_document(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": 500}],
        fmt="xlsx",
    )

    assert name.endswith(".xlsx") and data[:2] == b"PK"
    assert len(seen) == 1 and isinstance(seen[0], model.SheetModel)
