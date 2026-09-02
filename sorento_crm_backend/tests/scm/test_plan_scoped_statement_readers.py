"""BL-1 - every reader of a plan's statement stays inside that plan.

Migration 454 re-keyed the stock snapshot from `(company, supplier, item_code)` to
`(company, supplier, coalesce(loading_plan_id, nil), item_code)`, so one supplier can now
hold the SAME model number several times over: once per plan, plus the standalone
stock-list page's own supplier-wide row. Four readers were written when that could not
happen and each of them still selects the union:

* `GET /scm/supplier-inventory` (the standalone page) listed every plan's rows as if they
  were one snapshot, so the page showed duplicates and an `as_of` off whichever plan was
  newest;
* `supplier_document_model._snapshot` and `_snapshot_bindings` build `{item_code: ...}`
  dicts, so duplicates collapse onto an arbitrary winner - and that is the document SENT
  to the factory;
* `supplier_notice_service._held_by_item_code` does the same on the PUBLIC link payload.

The fallback half of the same defect is `test_plan_statement_fallback.py` (BL-2).

TEST-FIRST: `plan_statement` and the `loading_plan_id` arguments on the document builder and
the notice sheet do not exist when this file is written. Red first, as a missing keyword or
another plan's number, never as a wrong number quietly accepted.

Postgres via `pg_session` / `scm_app` (both rolled back), every chain seeded here under the
`ZZPO` marker the S6 suite already uses - CI's database has no data.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.models.supplier_notice import SupplierNotice
from app.services.scm import supplier_document_model as doc_model
from app.services.scm import supplier_inventory_service as stock_svc
from app.services.scm import supplier_notice_service as notice_svc
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import require_aliases
from tests.scm.conftest import requires_pg
from tests.scm.test_outstanding_import_routes import as_company_user
from tests.scm.test_plan_owned_statement import World

pytestmark = requires_pg

#: Their sheet's own header, the six columns the stock-list reader resolves.
_THEIR_HEADER = ["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def _their_sheet(rows: list[tuple[str, float]]) -> bytes:
    """A stock list in the supplier's own shape, for the document builder to answer in."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(_THEIR_HEADER))
    for code, packed in rows:
        ws.append([code, code, packed, 0, None, None])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _held(sheet: doc_model.SheetModel, item_code: str) -> float | None:
    """What the document says they hold of one model, off their own 包装好库存 column."""
    code_at = sheet.column_index("item_code")
    packed_at = sheet.column_index("qty_packed")
    row = next(r for r in sheet.rows if r.cells[code_at].value == item_code)
    return row.cells[packed_at].value


# --------------------------------------------------------------------------- #
# BL-1 - the standalone stock-list page
# --------------------------------------------------------------------------- #


def test_the_standalone_page_lists_only_the_rows_no_plan_owns():
    """The page is not a plan: it reads the supplier-wide snapshot, `loading_plan_id IS NULL`.

    With the union it listed the same model three times and dated the snapshot off whichever
    plan happened to be newest.
    """
    with pg_session() as db:
        w = World(db)
        w.stock_row("A", packed=10, plan_id=None, as_of=date(2026, 7, 31))
        w.stock_row("A", packed=20, plan_id=str(w.plan("stock_list").id), as_of=date(2026, 8, 28))
        w.stock_row("A", packed=30, plan_id=str(w.plan("stock_list").id), as_of=date(2026, 8, 29))

        out = stock_svc.snapshot(db, supplier_id=str(w.supplier.id))

        assert [r["item_code"] for r in out["rows"]] == [w.code("A")]
        assert out["rows"][0]["qty_packed"] == 10.0
        assert out["as_of"] == date(2026, 7, 31)


def test_the_standalone_page_route_answers_the_supplier_wide_snapshot(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    w.stock_row("A", packed=10, plan_id=None)
    w.stock_row("A", packed=20, plan_id=str(w.plan("stock_list").id))

    r = TestClient(app).get(
        "/api/v1/scm/supplier-inventory", params={"supplier_id": str(w.supplier.id)}
    )

    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert [x["qty_packed"] for x in rows] == [10.0]


# --------------------------------------------------------------------------- #
# BL-1 - the document that goes to the factory
# --------------------------------------------------------------------------- #


def test_the_no_file_document_reads_this_plans_own_snapshot(monkeypatch):
    """The "no file" branch of the document SENT to the supplier (`_snapshot`).

    Two plans hold the same model at different quantities; the sheet must state the one
    belonging to the plan being sent, not whichever row the dict happened to keep.
    """
    with pg_session() as db:
        w = World(db)
        mine, theirs = w.plan("stock_list"), w.plan("stock_list")
        w.stock_row("A", packed=40, plan_id=str(mine.id))
        w.stock_row("A", packed=900, plan_id=str(theirs.id))
        monkeypatch.setattr(doc_model, "_retained_stock_list", lambda _db, _sid: None)

        sheet = doc_model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[
                {
                    "product_id": str(w.product("A").id),
                    "item_code": w.code("A"),
                    "product_name": "A",
                    "qty": 5,
                }
            ],
            loading_plan_id=str(mine.id),
        )

        assert _held(sheet, w.code("A")) == 40.0


def test_the_ask_binds_through_this_plans_own_rows(monkeypatch):
    """`_snapshot_bindings`: their code, bound to OUR product, on the plan's own row.

    The same supplier code is bound to a different product under each plan (a corrected
    match on the newer upload). The ask for the FIRST plan's product has to land on their
    row rather than be appended under it as a model they never listed.
    """
    with pg_session() as db:
        require_aliases(db, "supplier_inventory")
        w = World(db)
        mine, theirs = w.plan("stock_list"), w.plan("stock_list")
        their_code = f"ZZPO-THEIRS-{w.tag}"
        w.stock_row("MINE", packed=4, plan_id=str(mine.id), item_code=their_code)
        w.stock_row("THEIRS", packed=9, plan_id=str(theirs.id), item_code=their_code)
        monkeypatch.setattr(
            doc_model,
            "_retained_stock_list",
            lambda _db, _sid: _their_sheet([(their_code, 4)]),
        )

        sheet = doc_model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[
                {
                    "product_id": str(w.product("MINE").id),
                    "item_code": w.code("MINE"),
                    "product_name": "MINE",
                    "qty": 7,
                }
            ],
            loading_plan_id=str(mine.id),
        )

        code_at = sheet.column_index("item_code")
        row = next(r for r in sheet.rows if r.cells[code_at].value == their_code)
        assert row.cells[-1].value == 7
        assert not any(r.appended for r in sheet.rows)


# --------------------------------------------------------------------------- #
# BL-1 - the public link the supplier opens
# --------------------------------------------------------------------------- #


def test_the_public_page_shows_the_holdings_of_the_plan_that_was_sent(scm_app, monkeypatch):
    """`_held_by_item_code` on the payload a factory reads through a leaked-proof token."""
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    monkeypatch.setattr(notice_svc, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(notice_svc, "_store", lambda data, filename: ("s3", f"t/{filename}"))
    w = World(db)
    w.supplier.email = f"zzpo-{uuid.uuid4().hex[:6]}@example.test"
    db.flush()
    mine, theirs = w.plan("stock_list"), w.plan("stock_list")
    w.stock_row("A", packed=40, plan_id=str(mine.id))
    w.stock_row("A", packed=900, plan_id=str(theirs.id))

    notice_svc.request_and_notify(
        db,
        supplier_id=str(w.supplier.id),
        lines=[{"product_id": str(w.product("A").id), "qty": 5}],
        loading_plan_id=str(mine.id),
    )
    notice = (
        db.query(SupplierNotice)
        .filter(SupplierNotice.loading_plan_id == str(mine.id))
        .one()
    )

    page = notice_svc.public_request_page(db, notice.public_token)

    assert [ln["qty_packed"] for ln in page["lines"]] == [40.0]
