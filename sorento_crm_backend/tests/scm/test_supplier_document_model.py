"""S4 / R12 - ONE sheet model behind the xlsx, the PDF and the public page.

`PLAN-scm-fulfilment-feedback-p4.md` section 4, AC-D1 .. AC-D7. The model is what makes the
three renderers agree: it is built once from the supplier's own retained stock list (their
title, their header spellings, their row order, their merges, their fills) with our one
column appended, and every renderer draws it.

The fixture is the real July file the captain sent, committed under
`documentation/plans/scm/fixtures/`. Its facts are asserted here rather than described,
because "the document tallies 100% with 库存明细.xlsx" is the acceptance criterion and a
description of a file is not a check on one.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.models.scm import SupplierInventory
from app.services.scm import supplier_document_model as model
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import require_aliases
from tests.scm.test_loading_plan import World

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "documentation"
    / "plans"
    / "scm"
    / "fixtures"
    / "jinbaichuan-stock-list-2026-07-27.xlsx"
)

#: Their ten columns, in their order, as row 2 of the fixture writes them.
THEIR_COLUMNS = [
    "序号",
    "型号",
    "商标",
    "规格",
    "品名",
    "包装好库存",
    "空瓷",
    "体积(cbm)",
    "总体积(cbm)",
    "备注",
]

SUPPLIER = {"supplier_code": "JBC", "supplier_name": "JINBAICHUAN"}


def _their_sheet() -> bytes:
    return FIXTURE.read_bytes()


def _world(db) -> World:
    require_aliases(db, "supplier_inventory")
    return World(db)


def _built(db, lines: list[dict], *, monkeypatch, sheet: bytes | None = None):
    monkeypatch.setattr(
        model, "_retained_stock_list", lambda _db, _sid, **_kw: sheet if sheet else _their_sheet()
    )
    return model.build(db, supplier_id=str(uuid.uuid4()), lines=lines)


def _row_for(sheet: model.SheetModel, item_code: str) -> model.Row:
    col = sheet.column_index("item_code")
    return next(r for r in sheet.rows if r.cells[col].value == item_code)


def _line(item_code: str, qty: float, *, product_id: str | None = None) -> dict:
    return {
        "item_code": item_code,
        "product_name": f"{item_code} name",
        "qty": qty,
        "product_id": product_id,
    }


# --------------------------------------------------------------------------- #
# their sheet
# --------------------------------------------------------------------------- #


def test_the_columns_are_theirs_plus_ours(monkeypatch):
    # AC-D1. Their ten spellings untouched, in their order, and column K appended (Q1).
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [], monkeypatch=monkeypatch)

        assert [c.label for c in sheet.columns] == THEIR_COLUMNS + [
            model.QTY_TO_LOAD_LABEL_ZH
        ]
        assert sheet.columns[-1].label_en == model.QTY_TO_LOAD_LABEL_EN
        assert sheet.title == "金百川库存表 2026年7月27日"


def test_a_family_becomes_a_rowspan_on_their_merged_columns(monkeypatch):
    # AC-D1 / AC-D4. `A3:A11`, `H3:H11`, `I3:I11` is ONE product family: nine rows under one
    # 序号 and one volume. A model that lost the merge would print the volume nine times,
    # which reads as nine times the volume.
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [], monkeypatch=monkeypatch)

        first, second = sheet.rows[0], sheet.rows[1]
        assert first.cells[0].rowspan == 9 and first.family_span == 9
        assert first.cells[7].rowspan == 9  # 体积(cbm), H3:H11
        assert first.cells[8].rowspan == 9  # 总体积(cbm), I3:I11
        assert second.cells[0].covered is True and second.family_span == 0
        assert second.cells[8].covered is True


def test_their_fills_and_their_red_figures_are_carried(monkeypatch):
    # AC-D1 / AC-D5. B:G and J are yellow on their sheet and a figure they want us to notice
    # is red. Both are their own marks on their own document; a renderer that dropped them
    # would hand back a sheet that no longer says what theirs said.
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [], monkeypatch=monkeypatch)

        first = _row_for(sheet, "SRTWC286-SH-150NEW")
        assert first.cells[1].fill == "yellow"  # 型号
        assert first.cells[5].fill == "yellow"  # 包装好库存
        assert first.cells[5].value == 0 and first.cells[5].red is True
        assert first.cells[7].fill is None  # 体积(cbm) is not filled


def test_the_ask_lands_on_their_row_by_their_own_code(monkeypatch):
    # AC-D3 / AC-F12.6. A set line goes out under the supplier's own code, which is the code
    # their sheet already carries, so the quantity belongs on THEIR row - never appended.
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [_line("SRTWC8355-RL-250", 300)], monkeypatch=monkeypatch)

        asked = _row_for(sheet, "SRTWC8355-RL-250")
        assert asked.cells[-1].value == 300
        assert asked.appended is False
        assert not any(r.appended for r in sheet.rows)


def test_the_ask_lands_on_their_row_through_the_snapshot_binding(monkeypatch):
    # AC-D3. Their code and our product code are different strings; the snapshot row is what
    # binds them. Matching on the string alone would append a row they already list.
    with pg_session() as db:
        w = _world(db)
        product = w.product("A")
        db.add(
            SupplierInventory(
                id=str(uuid.uuid4()),
                supplier_id=w.supplier.id,
                item_code="SRTSP131",
                product_id=product.id,
                qty_packed=2,
                qty_unfinished=0,
                as_of=__import__("datetime").date(2026, 7, 27),
            )
        )
        db.flush()
        monkeypatch.setattr(model, "_retained_stock_list", lambda _db, _sid, **_kw: _their_sheet())

        sheet = model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[_line(product.product_code, 11, product_id=str(product.id))],
        )

        assert _row_for(sheet, "SRTSP131").cells[-1].value == 11
        assert not any(r.appended for r in sheet.rows)


def test_a_zero_ask_leaves_the_cell_empty(monkeypatch):
    # AC-D3 (AC-C3 of part 3 stands). A zero reads as "pack none of these", which is a
    # different instruction from "we did not ask about these".
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [_line("SRTWC8355-RL-250", 0)], monkeypatch=monkeypatch)

        assert _row_for(sheet, "SRTWC8355-RL-250").cells[-1].value is None


def test_a_product_they_never_listed_is_appended_with_a_continuing_serial(monkeypatch):
    # AC-D2. It is still part of the ask; dropping it because their own sheet has no line
    # for it is how a container goes out short.
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [_line("ZZT-NOT-ON-LIST", 80)], monkeypatch=monkeypatch)

        appended = [r for r in sheet.rows if r.appended]
        assert len(appended) == 1
        row = appended[0]
        assert row.cells[0].value == 39  # their last 序号 is 38
        assert row.cells[1].value == "ZZT-NOT-ON-LIST"
        assert row.cells[-1].value == 80
        assert row.cells[sheet.column_index("remark")].value == model.NOT_ON_LIST_REMARK
        assert sheet.rows[-1] is row


def test_the_totals_row_sums_what_theirs_sums_and_our_column(monkeypatch):
    # AC-D1. Their 合计 row sums 包装好库存, 空瓷 and 总体积 and nothing else; ours adds K.
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [_line("SRTWC8355-RL-250", 300)], monkeypatch=monkeypatch)

        totals = sheet.totals
        assert totals is not None
        assert totals.cells[0].value == "合计："
        assert totals.cells[0].colspan == 5
        packed = sum(
            c.value
            for c in (r.cells[5] for r in sheet.rows)
            if isinstance(c.value, (int, float))
        )
        assert totals.cells[5].value == packed
        assert totals.cells[3].value is None  # 规格 has no total on their sheet
        assert totals.cells[-1].value == 300


# --------------------------------------------------------------------------- #
# no retained file
# --------------------------------------------------------------------------- #


def test_without_a_retained_file_the_columns_are_the_same_eleven(monkeypatch):
    # AC-D6. The five-column sheet of our own is gone: a supplier who reads one document from
    # us must not get a different document because of a file WE failed to keep.
    with pg_session() as db:
        w = _world(db)
        monkeypatch.setattr(model, "_retained_stock_list", lambda _db, _sid, **_kw: None)

        sheet = model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[_line(w.product("A").product_code, 500)],
        )

        assert [c.label for c in sheet.columns] == THEIR_COLUMNS + [
            model.QTY_TO_LOAD_LABEL_ZH
        ]
        assert sheet.source is None
        assert all(c.rowspan == 1 and not c.covered for r in sheet.rows for c in r.cells)


def test_without_a_retained_file_the_row_states_what_we_know(monkeypatch):
    # AC-D6. 商标 = the company letter the product belongs to, 品名 = its name, and their own
    # holdings come off the snapshot - the honest thing to show them about their warehouse.
    with pg_session() as db:
        w = _world(db)
        product = w.product("A")
        product.company_id = "00000000-0000-0000-0000-000000000001"  # SRT
        w.stock("A", packed=120, unfinished=340, cbm=0.21)
        db.flush()
        monkeypatch.setattr(model, "_retained_stock_list", lambda _db, _sid, **_kw: None)

        sheet = model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[_line(product.product_code, 500, product_id=str(product.id))],
        )

        row = sheet.rows[0]
        assert row.cells[0].value == 1
        assert row.cells[1].value == product.product_code
        assert row.cells[2].value == "S"
        assert row.cells[4].value == f"{product.product_code} name"
        assert row.cells[5].value == 120
        assert row.cells[6].value == 340
        assert row.cells[7].value == 0.21
        assert row.cells[-1].value == 500


def test_without_a_retained_file_a_zero_holding_is_still_red(monkeypatch):
    # AC-D6. Their own convention for "none packed", kept on the document we build for them.
    with pg_session() as db:
        w = _world(db)
        w.stock("A", packed=0, unfinished=12)
        monkeypatch.setattr(model, "_retained_stock_list", lambda _db, _sid, **_kw: None)

        sheet = model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[_line(w.product("A").product_code, 500)],
        )

        assert sheet.rows[0].cells[5].value == 0
        assert sheet.rows[0].cells[5].red is True


def test_a_stored_file_that_will_not_open_falls_back_rather_than_failing(monkeypatch):
    # A send must never die because a stored file is corrupt: the ask is the point.
    with pg_session() as db:
        w = _world(db)
        monkeypatch.setattr(model, "_retained_stock_list", lambda _db, _sid, **_kw: b"not a workbook")

        sheet = model.build(
            db,
            supplier_id=str(w.supplier.id),
            lines=[_line(w.product("A").product_code, 500)],
        )

        assert sheet.source is None
        assert [c.label for c in sheet.columns] == THEIR_COLUMNS + [
            model.QTY_TO_LOAD_LABEL_ZH
        ]


def test_the_model_serialises_for_the_public_page(monkeypatch):
    # AC-D5 / AC-D7. The page renders the SAME model, so it travels as JSON: cells with their
    # rowspan, their fill and their red, and the 合计 row.
    with pg_session() as db:
        _world(db)
        sheet = _built(db, [_line("SRTWC8355-RL-250", 300)], monkeypatch=monkeypatch)

        payload = sheet.to_dict()

        import json

        json.dumps(payload)  # no Decimal, no date, nothing the page cannot read
        assert payload["title"] == "金百川库存表 2026年7月27日"
        assert payload["columns"][-1] == {
            "label": model.QTY_TO_LOAD_LABEL_ZH,
            "label_en": model.QTY_TO_LOAD_LABEL_EN,
        }
        first = payload["rows"][0]
        assert first["cells"][0]["rowspan"] == 9
        assert first["family_span"] == 9
        assert payload["rows"][1]["cells"][0]["covered"] is True
        assert payload["totals"]["cells"][0]["value"] == "合计："
