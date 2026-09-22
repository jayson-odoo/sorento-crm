"""RED tests, written before the coder's Phase 2, for the one-off backfill script
`scripts/backfill_order_back_rows.py` (`PLAN-oi-order-back-not-capped.md`, R4/S4).

AC-OB-13/14/15/16. The script does not exist yet, so importing it fails the WHOLE FILE at
collection with one `ImportError` - every case below is red for that reason until S4 lands.

Contract (captain's test list): `run(db, xlsx_paths: list[str], apply: bool) -> list[dict]`,
one dict per candidate `{so_number, item_code, qty, stock_location, action}`, where
`action` is `"flipped"` | `"skipped_person_actioned"` | `"unmatched"`. Dry run (the default,
``apply=False``) writes nothing. ``apply=True`` flips only a row the OLD importer bug closed
the same second it raised it (``actioned_at == order_inquiries.raised_at``) whose matching
sheet row (same so_number, item_code, qty, delivery_date, stock_location) reads ORDER BACK -
setting verb ORDER_BACK, state raised, actioned_by/actioned_at NULL, and the header state
back to raised. A row a PERSON marked actioned (``actioned_at`` differs from ``raised_at``)
is never touched, even when its own sheet row reads ORDER BACK too (R4).

Postgres only (`tests/_pg_fixture.py::pg_session`), every FK chain seeded here behind the
ZZT-OBBF marker - CI's database is empty, nothing is borrowed off an existing row.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User

from ._pg_fixture import pg_session

# THE red import - `scripts/backfill_order_back_rows.py` does not exist yet (S4).
import scripts.backfill_order_back_rows as backfill  # noqa: E402

MARKER = "ZZT-OBBF"
HEADERS = ("SO NO", "ITEM CODE", "QTY", "DELIVERY DATE", "STOCK LOCATION", "REMARK")


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _sheet_bytes(rows) -> bytes:
    """A minimal single-sheet-form workbook: SO NO, ITEM CODE, QTY, DELIVERY DATE,
    STOCK LOCATION, REMARK - the customer's own single-sheet shape."""
    import openpyxl

    wb = openpyxl.Workbook()
    tab = wb.active
    tab.title = "Sheet1"
    tab.append(list(HEADERS))
    for row in rows:
        tab.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _uploader(db) -> str:
    row = User(id=_uid(), email=f"{_uid()}@zzt.test", name=f"{MARKER} uploader")
    db.add(row)
    db.flush()
    return row.id


def _order_back_candidate(
    db,
    company_id,
    uploader,
    *,
    so_number,
    item_code="ZZT-ITEM",
    qty="3",
    delivery_date=date(2026, 9, 20),
    stock_location="BRW-BB",
    actioned_offset: timedelta | None = None,
    actioned_by: str | None = None,
    so_line_id=None,
    pso=None,
):
    """One header + one ORDER row, shaped exactly as the pre-fix importer left SO417310 /
    MKT5529SS-DIY: `state='actioned'`, `actioned_at` stamped in the SAME instant as the
    header's own `raised_at`, `actioned_by` the SAME principal as the header's own
    `raised_by`. `actioned_offset` names a person's own LATER action instead - the shape
    R4 says must never be touched. `actioned_by` overrides the actor to a DIFFERENT
    principal from the uploader - the "purchasing marked it by hand" shape, distinct from
    a person's own later click even when it happens to land inside the clock window.
    `pso` reuses an ALREADY-BUILT `ProjectSalesOrder` (and its own core `SalesOrder`)
    instead of minting a fresh pair - for a test that needs a core line/mirror under the
    same SO before the inquiry row exists (`uq_sales_orders_company_so_number` refuses a
    second core row for the same `(company_id, so_number)`).
    """
    if pso is None:
        core = SalesOrder(id=_uid(), company_id=company_id, so_number=so_number, status="open")
        db.add(core)
        db.flush()
        pso = ProjectSalesOrder(
            id=_uid(), company_id=company_id, provisional_ref=f"{MARKER}-PSO-{_uid()[:8]}",
            so_id=core.id, status="published",
        )
        db.add(pso)
        db.flush()
    raised_at = datetime(2026, 9, 20, 11, 19, 23)
    inquiry = OrderInquiry(
        id=_uid(), company_id=company_id, inquiry_no=f"OI-{MARKER}-{_uid()[:6]}",
        project_sales_order_id=pso.id, state=INQUIRY_ACTIONED, raised_by=uploader,
        raised_at=raised_at,
    )
    db.add(inquiry)
    db.flush()
    actioned_at = raised_at if actioned_offset is None else raised_at + actioned_offset
    row = OrderInquiryRow(
        id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id, so_line_id=so_line_id,
        item_code=item_code, qty=Decimal(qty), delivery_date=delivery_date,
        stock_location=stock_location, verb=IV_ORDER, state=INQUIRY_ACTIONED,
        actioned_by=actioned_by if actioned_by is not None else uploader,
        actioned_at=actioned_at,
    )
    db.add(row)
    db.flush()
    return {"pso": pso, "inquiry": inquiry, "row": row}


def test_ac_ob_13_a_dry_run_prints_the_candidate_and_writes_nothing(tmp_path):
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO1-{_uid()[:6]}"
        world = _order_back_candidate(db, company_id, uploader, so_number=so_number)
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        expected_actioned_at = world["row"].actioned_at

        result = backfill.run(db, [str(path)], apply=False)

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips, result
        assert flips[0]["action"] == "flipped"
        assert flips[0]["item_code"] == "ZZT-ITEM"
        assert Decimal(str(flips[0]["qty"])) == Decimal("3")
        assert flips[0]["stock_location"] == "BRW-BB"

        # The dry run's real contract is the DATABASE, not just the report: `run()`
        # never calls `db.commit()` when `apply=False` (every write is gated `if apply`),
        # so expiring the identity map and re-reading straight from Postgres must show
        # the row and its header exactly as `_order_back_candidate` left them.
        db.expire_all()
        row = db.get(OrderInquiryRow, world["row"].id)
        assert row.verb == IV_ORDER, "a dry run must write nothing"
        assert row.state == INQUIRY_ACTIONED
        assert row.actioned_at == expected_actioned_at
        inquiry = db.get(OrderInquiry, world["inquiry"].id)
        assert inquiry.state == INQUIRY_ACTIONED


def test_ac_ob_14_apply_flips_the_importer_closed_row(tmp_path):
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO2-{_uid()[:6]}"
        world = _order_back_candidate(db, company_id, uploader, so_number=so_number)
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "flipped", result

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER_BACK
        assert world["row"].state == INQUIRY_RAISED
        assert world["row"].actioned_by is None
        assert world["row"].actioned_at is None

        db.refresh(world["inquiry"])
        assert world["inquiry"].state == INQUIRY_RAISED


def test_ac_ob_15_a_person_marked_actioned_row_is_never_flipped(tmp_path):
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO3-{_uid()[:6]}"
        world = _order_back_candidate(
            db, company_id, uploader, so_number=so_number,
            actioned_offset=timedelta(hours=3),
        )
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips, result
        assert flips[0]["action"] == "skipped_person_actioned", flips

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER, "a person's own action must never be flipped"
        assert world["row"].state == INQUIRY_ACTIONED
        assert world["row"].actioned_by == uploader


def test_ac_ob_15b_the_8h_myt_skew_with_the_same_actor_still_flips(tmp_path):
    """Prod row bee581f3's own shape (module docstring, CLOCK bullet): `actioned_at` sits
    8h + 30s after `raised_at` - the S5a timezone bug's skew, not a person's later click -
    and `actioned_by` is the SAME principal as the header's own `raised_by`. Still an
    importer close, so it still flips."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO4-{_uid()[:6]}"
        world = _order_back_candidate(
            db, company_id, uploader, so_number=so_number,
            actioned_offset=timedelta(hours=8, seconds=30),
        )
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "flipped", result

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER_BACK


def test_ac_ob_15c_the_8h_myt_skew_with_a_different_actor_is_skipped(tmp_path):
    """Same 8h + 30s clock shape as above, but `actioned_by` is a DIFFERENT principal from
    the header's own `raised_by` - a purchasing user marking the row actioned by hand, who
    happened to click inside the clock window. Never flipped (R4's principal test)."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        purchasing_user = _uploader(db)
        so_number = f"{MARKER}-SO5-{_uid()[:6]}"
        world = _order_back_candidate(
            db, company_id, uploader, so_number=so_number,
            actioned_offset=timedelta(hours=8, seconds=30), actioned_by=purchasing_user,
        )
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "skipped_person_actioned", flips

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER, "a different actor's action must never flip"
        assert world["row"].actioned_by == purchasing_user


def test_ac_ob_15d_outside_both_clock_windows_is_skipped(tmp_path):
    """8h + 5 minutes: outside BOTH the exact-match window and the MYT-skew window, same
    actor or not. A person's own later action, not the importer."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO6-{_uid()[:6]}"
        world = _order_back_candidate(
            db, company_id, uploader, so_number=so_number,
            actioned_offset=timedelta(hours=8, minutes=5),
        )
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "skipped_person_actioned", flips

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER


def test_ac_ob_14b_blank_location_cell_matches_the_core_lines_own_location_and_flips(tmp_path):
    """Point 4/N2/N5 fix round (AC-OB-14 territory - AC-OB-4 is the view test, not this
    script). The sheet's STOCK LOCATION cell is blank today, but the DB row carries the
    CORE LINE's own warehouse code - exactly what the importer's own `raise_row` fallback
    (`stock_location=location or match.line_location`) would have written when the sheet
    was first uploaded with that same blank cell. The match must fall back the same way,
    or a legitimately-imported row can never be found again.

    The WAREHOUSE's own `warehouse_code` is stored in a DIFFERENT case from the row's
    `stock_location` (which `raise_row` always upper-cases) - N5's own case, proving the
    match's `func.upper(Warehouse.warehouse_code)` normalises the side that carries no
    such guarantee rather than relying on both already agreeing.
    """
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO7-{_uid()[:6]}"

        warehouse_code = f"{MARKER}-WH-{_uid()[:6]}".upper()
        warehouse = Warehouse(
            id=_uid(), company_id=company_id, warehouse_code=warehouse_code.lower(),
            warehouse_name=warehouse_code, is_active=True,
        )
        db.add(warehouse)
        cat_id, uom_id, product_id = _uid(), _uid(), _uid()
        db.execute(text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:i, :c, :c)"), {"i": cat_id, "c": f"{MARKER}-CAT-{cat_id[:6]}"})
        db.execute(text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, :c)"),
            {"i": uom_id, "c": f"{MARKER}-U-{uom_id[:6]}"})
        db.execute(text(
            "INSERT INTO products (id, company_id, product_code, product_name, "
            "category_id, base_uom_id, list_price) "
            "VALUES (:i, :c, :code, :code, :cat, :uom, 0)"),
            {"i": product_id, "c": company_id, "code": f"{MARKER}-P-{product_id[:6]}",
             "cat": cat_id, "uom": uom_id})
        db.flush()
        core = SalesOrder(
            id=_uid(), company_id=company_id, so_number=so_number, status="open",
        )
        db.add(core)
        db.flush()
        core_line = SalesOrderLine(
            id=_uid(), sales_order_id=core.id, product_id=product_id,
            warehouse_id=warehouse.id, qty_ordered=Decimal("3"), qty_delivered=Decimal("0"),
            line_status="open", company_id=company_id,
        )
        db.add(core_line)
        db.flush()
        pso = ProjectSalesOrder(
            id=_uid(), company_id=company_id, provisional_ref=f"{MARKER}-PSO-{_uid()[:8]}",
            so_id=core.id, status="published",
        )
        db.add(pso)
        db.flush()
        mirror = ProjectSalesOrderLine(
            id=_uid(), company_id=company_id, project_sales_order_id=pso.id, line_no=1,
            product_id=product_id, qty=Decimal("3"), unit_price=Decimal("0"),
            amount=Decimal("0"), core_sales_order_line_id=core_line.id,
        )
        db.add(mirror)
        db.flush()

        world = _order_back_candidate(
            db, company_id, uploader, so_number=so_number, pso=pso,
            # The row itself carries the FALLBACK value, the core line's own code - what
            # the importer would have written for a blank sheet cell.
            stock_location=warehouse_code, so_line_id=mirror.id,
        )
        db.commit()

        path = tmp_path / "sheet.xlsx"
        # STOCK LOCATION blank on today's re-read.
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "flipped", result

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER_BACK


def test_ac_ob_16_a_sheet_row_with_no_matching_inquiry_row_is_reported_unmatched(tmp_path):
    with pg_session() as db:
        so_number = f"{MARKER}-SO-GHOST-{_uid()[:6]}"
        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-GHOST-ITEM", 9, date(2026, 9, 1), "BRW-AA", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        ghosts = [r for r in result if r["so_number"] == so_number]
        assert ghosts, result
        assert ghosts[0]["action"] == "unmatched"

        created = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.item_code == "ZZT-GHOST-ITEM")
            .count()
        )
        assert created == 0, "a sheet row with nothing to match must never be created"


def test_n1_a_duplicated_sheet_row_dedupes_on_both_dry_run_and_apply(tmp_path):
    """N1 fix round. The SAME sheet row twice (identical SO/item/qty/date/location): a
    dry run reports the candidate ONCE, and `--apply` reports it twice - `flipped` then
    `already_flipped` - never re-entering the mutation branch and never mislabelling the
    repeat as `skipped_person_actioned` or `unmatched` (the flush-then-requery race N1
    fixed). The row itself is flipped exactly once."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO8-{_uid()[:6]}"
        world = _order_back_candidate(db, company_id, uploader, so_number=so_number)
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        dry = backfill.run(db, [str(path)], apply=False)
        dry_actions = [r["action"] for r in dry if r["so_number"] == so_number]
        assert dry_actions == ["flipped"], dry

        applied = backfill.run(db, [str(path)], apply=True)
        db.commit()
        applied_actions = [r["action"] for r in applied if r["so_number"] == so_number]
        assert applied_actions == ["flipped", "already_flipped"], applied

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER_BACK
        assert world["row"].state == INQUIRY_RAISED


def test_n3_a_blank_delivery_date_cell_matches_the_core_lines_required_date_and_flips(
    tmp_path,
):
    """Point 3 fix round: the sheet's DELIVERY DATE cell is blank today, but the DB row
    carries the CORE LINE's own `required_date` - exactly what `raise_row`'s own fallback
    (`delivery_date=row.delivery_date or match.core_line.required_date`) would have
    written when the sheet was first uploaded with that same blank cell."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SO9-{_uid()[:6]}"

        cat_id, uom_id, product_id = _uid(), _uid(), _uid()
        db.execute(text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:i, :c, :c)"), {"i": cat_id, "c": f"{MARKER}-CAT-{cat_id[:6]}"})
        db.execute(text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, :c)"),
            {"i": uom_id, "c": f"{MARKER}-U-{uom_id[:6]}"})
        db.execute(text(
            "INSERT INTO products (id, company_id, product_code, product_name, "
            "category_id, base_uom_id, list_price) "
            "VALUES (:i, :c, :code, :code, :cat, :uom, 0)"),
            {"i": product_id, "c": company_id, "code": f"{MARKER}-P-{product_id[:6]}",
             "cat": cat_id, "uom": uom_id})
        db.flush()
        required_date = date(2026, 10, 5)
        core = SalesOrder(id=_uid(), company_id=company_id, so_number=so_number, status="open")
        db.add(core)
        db.flush()
        core_line = SalesOrderLine(
            id=_uid(), sales_order_id=core.id, product_id=product_id,
            required_date=required_date, qty_ordered=Decimal("3"),
            qty_delivered=Decimal("0"), line_status="open", company_id=company_id,
        )
        db.add(core_line)
        db.flush()
        pso = ProjectSalesOrder(
            id=_uid(), company_id=company_id, provisional_ref=f"{MARKER}-PSO-{_uid()[:8]}",
            so_id=core.id, status="published",
        )
        db.add(pso)
        db.flush()
        mirror = ProjectSalesOrderLine(
            id=_uid(), company_id=company_id, project_sales_order_id=pso.id, line_no=1,
            product_id=product_id, qty=Decimal("3"), unit_price=Decimal("0"),
            amount=Decimal("0"), core_sales_order_line_id=core_line.id,
        )
        db.add(mirror)
        db.flush()

        world = _order_back_candidate(
            db, company_id, uploader, so_number=so_number, pso=pso,
            # The row itself carries the FALLBACK value, the core line's own required_date.
            delivery_date=required_date, so_line_id=mirror.id,
        )
        db.commit()

        path = tmp_path / "sheet.xlsx"
        # DELIVERY DATE blank on today's re-read.
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, "", "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True)
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "flipped", result

        db.refresh(world["row"])
        assert world["row"].verb == IV_ORDER_BACK


def _two_company_candidates(db, uploader, so_number):
    """The SAME SO number, and the SAME importer-closed ORDER row shape, in TWO different
    companies - the ambiguity `--apply` must refuse without `--company`.

    `tests/conftest.py`'s own session-start listener defaults every test session's
    company scope to SRT alone (`_default_company_scope_for_tests`) - fail-closed is the
    right default, but it would also scope the SECOND company's row out of every read a
    caller of this helper makes THROUGH THIS SESSION, same as `backfill.main()` itself
    widens it (`set_company_scope(db, None)`) for the very reason a script has no request
    and no principal to scope by.
    """
    set_company_scope(db, None)
    srt = _sorento(db)
    other = db.execute(text(
        "INSERT INTO companies (id, name, code, is_active, created_at) "
        "VALUES (:i, :n, :c, true, now()) RETURNING id"
    ), {"i": _uid(), "n": f"{MARKER} co", "c": f"{MARKER[:8]}{_uid()[:6]}".replace("-", "")}
    ).scalar()
    world_a = _order_back_candidate(db, srt, uploader, so_number=so_number)
    world_b = _order_back_candidate(db, other, uploader, so_number=so_number)
    db.commit()
    return {"srt": srt, "other": other, "a": world_a, "b": world_b}


def test_n2_ambiguous_so_number_refuses_apply_and_writes_nothing(tmp_path):
    with pg_session() as db:
        uploader = _uploader(db)
        so_number = f"{MARKER}-SOA-{_uid()[:6]}"
        world = _two_company_candidates(db, uploader, so_number)

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        # No rollback needed: the ambiguity check runs BEFORE any query that could
        # match a row, let alone mutate one, so there is nothing to undo - the same
        # reason `run()` itself never rolls back a dry run (see SAFETY / IDEMPOTENCY).
        with pytest.raises(backfill.AmbiguousCompanyError):
            backfill.run(db, [str(path)], apply=True)

        db.refresh(world["a"]["row"])
        db.refresh(world["b"]["row"])
        assert world["a"]["row"].verb == IV_ORDER
        assert world["b"]["row"].verb == IV_ORDER


def test_n2_ambiguous_so_number_with_company_flips_only_that_company(tmp_path):
    with pg_session() as db:
        uploader = _uploader(db)
        so_number = f"{MARKER}-SOB-{_uid()[:6]}"
        world = _two_company_candidates(db, uploader, so_number)

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=True, company_code="SRT")
        db.commit()

        flips = [r for r in result if r["so_number"] == so_number]
        assert flips and flips[0]["action"] == "flipped", result
        assert flips[0]["company_code"] == "SRT"

        db.refresh(world["a"]["row"])
        db.refresh(world["b"]["row"])
        assert world["a"]["row"].verb == IV_ORDER_BACK
        assert world["b"]["row"].verb == IV_ORDER, "the OTHER company's row must never move"


def test_n2_ambiguous_so_number_dry_run_lists_both_companies(tmp_path):
    with pg_session() as db:
        uploader = _uploader(db)
        so_number = f"{MARKER}-SOC-{_uid()[:6]}"
        _two_company_candidates(db, uploader, so_number)

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        result = backfill.run(db, [str(path)], apply=False)
        rows = [r for r in result if r["so_number"] == so_number]
        assert len(rows) == 2, rows
        codes = {r["company_code"] for r in rows}
        assert len(codes) == 2, "both companies must be listed, distinctly"
        assert all(r["action"] == "flipped" for r in rows)


def test_n2_main_returns_2_on_ambiguous_company(tmp_path, capsys):
    with pg_session() as db:
        uploader = _uploader(db)
        so_number = f"{MARKER}-SOD-{_uid()[:6]}"
        _two_company_candidates(db, uploader, so_number)

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        code = backfill.main(["--apply", str(path)], db=db)
        db.rollback()

        assert code == 2
        out = capsys.readouterr().out
        assert "REFUSING" in out


def test_n4_main_returns_2_on_unknown_company_code(tmp_path, capsys):
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        so_number = f"{MARKER}-SOE-{_uid()[:6]}"
        _order_back_candidate(db, company_id, uploader, so_number=so_number)
        db.commit()

        path = tmp_path / "sheet.xlsx"
        path.write_bytes(_sheet_bytes([
            (so_number, "ZZT-ITEM", 3, date(2026, 9, 20), "BRW-BB", "order back"),
        ]))

        code = backfill.main(
            ["--apply", "--company", "ZZT-NOPE-CODE", str(path)], db=db,
        )
        db.rollback()

        assert code == 2
        out = capsys.readouterr().out
        assert "REFUSING" in out
        assert "ZZT-NOPE-CODE" in out
