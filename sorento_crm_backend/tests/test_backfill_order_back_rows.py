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

from sqlalchemy import text

from app.models.order import SalesOrder
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_RAISED,
    IV_ORDER,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
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
):
    """One header + one ORDER row, shaped exactly as the pre-fix importer left SO417310 /
    MKT5529SS-DIY: `state='actioned'`, `actioned_at` stamped in the SAME instant as the
    header's own `raised_at`. `actioned_offset` names a person's own LATER action instead -
    the shape R4 says must never be touched.
    """
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
        id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id, item_code=item_code,
        qty=Decimal(qty), delivery_date=delivery_date, stock_location=stock_location,
        verb=IV_ORDER, state=INQUIRY_ACTIONED, actioned_by=uploader, actioned_at=actioned_at,
    )
    db.add(row)
    db.flush()
    return {"core": core, "pso": pso, "inquiry": inquiry, "row": row}


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

        result = backfill.run(db, [str(path)], apply=False)

        # `run()`'s own dry-run branch ends in `db.rollback()` (the script's documented
        # write-prevention mechanism: "every candidate is read, classified and printed,
        # then the whole run is rolled back") - which, inside `pg_session`'s own harness,
        # expires every object in the session, so a post-hoc `db.refresh(world["row"])`
        # here would raise for the SAME reason the write-prevention works, not because of
        # a fixture bug. The observable dry-run contract is the RETURNED report.
        flips = [r for r in result if r["so_number"] == so_number]
        assert flips, result
        assert flips[0]["action"] == "flipped"
        assert flips[0]["item_code"] == "ZZT-ITEM"
        assert Decimal(str(flips[0]["qty"])) == Decimal("3")
        assert flips[0]["stock_location"] == "BRW-BB"


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
