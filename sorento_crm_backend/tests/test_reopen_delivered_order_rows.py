"""RED tests, written before the coder's Phase 2, for the one-off script
`scripts/reopen_delivered_order_rows.py` (`PLAN-oi-order-rows-uncapped.md`, S4).

AC-OU-10/11. The script does not exist yet, so importing it fails the WHOLE FILE at
collection with one `ModuleNotFoundError` - every case below is red for that reason
until S4 lands.

Contract (captain's test list): `run(db, *, delivery_from: date, company_code: str |
None, apply: bool) -> list[dict]`, one dict per candidate `{so_number, item_code, qty,
delivery_date, company_code, action}`, where `action` is `"reopened"` |
`"skipped_person_actioned"` | `"skipped_cancelled_line"` | `"skipped_before_from"`.
`main(argv, db=None) -> int` exits 2 when `--delivery-from` is not given.

A candidate is `verb IN (ORDER, ORDER_BACK)`, `state = actioned`, importer-closed -
`actioned_by == order_inquiries.raised_by` and `actioned_at` within 60 seconds of
`raised_at` OR of `raised_at + 8h` (the same two-signal test `backfill_order_back_
rows.py::_is_importer_closed` uses, R3/R4 precedent) - core line `line_status !=
cancelled`, `delivery_date >= --delivery-from`. `--apply` sets `state = raised`,
`actioned_by`/`actioned_at` NULL, and the row's own inquiry header back to `raised`. Dry
run (the default) writes nothing.

Postgres only (`tests/_pg_fixture.py::pg_session`), every FK chain seeded here behind
the ZZT-REOP marker - CI's database is empty, nothing is borrowed off an existing row.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

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

# THE red import - `scripts/reopen_delivered_order_rows.py` does not exist yet (S4).
import scripts.reopen_delivered_order_rows as reopen  # noqa: E402

MARKER = "ZZT-REOP"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _uploader(db) -> str:
    row = User(id=_uid(), email=f"{_uid()}@zzt.test", name=f"{MARKER} uploader")
    db.add(row)
    db.flush()
    return row.id


def _reopen_candidate(
    db,
    company_id,
    uploader,
    *,
    so_number=None,
    delivery_date=date(2026, 9, 15),
    line_status="closed",
    qty="3",
    verb=IV_ORDER,
    actioned_offset: timedelta | None = None,
    actioned_by: str | None = None,
):
    """One header + one importer-closed ORDER/ORDER_BACK row against a delivered core
    line - the SO421985 shape (plan section 1): raised while the line was still open,
    later closed by the SAME upload's own history-close (before this lane's R1/R2 fix),
    `actioned_at` stamped in the SAME instant as the header's own `raised_at`,
    `actioned_by` the SAME principal as the header's own `raised_by`.
    `actioned_offset` names a person's own LATER action instead - the shape the script
    must never touch. `actioned_by` overrides the actor to a DIFFERENT principal from
    the uploader.
    """
    so_number = so_number or f"{MARKER}-SO-{_uid()[:6]}"
    cat_id, uom_id, product_id, warehouse_id = _uid(), _uid(), _uid(), _uid()
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
    db.execute(text(
        "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
        "is_active) VALUES (:i, :c, :code, :code, true)"),
        {"i": warehouse_id, "c": company_id, "code": f"{MARKER}-WH-{warehouse_id[:6]}"})
    db.flush()

    core = SalesOrder(
        id=_uid(), company_id=company_id, so_number=so_number, status="open",
        demand_class="project",
    )
    db.add(core)
    db.flush()
    core_line = SalesOrderLine(
        id=_uid(), company_id=company_id, sales_order_id=core.id, product_id=product_id,
        warehouse_id=warehouse_id,
        qty_ordered=Decimal(qty), qty_delivered=Decimal(qty), line_status=line_status,
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
        product_id=product_id, qty=Decimal(qty), unit_price=Decimal("0"),
        amount=Decimal("0"), core_sales_order_line_id=core_line.id,
    )
    db.add(mirror)
    db.flush()
    raised_at = datetime(2026, 9, 15, 3, 0, 0)
    inquiry = OrderInquiry(
        id=_uid(), company_id=company_id, inquiry_no=f"OI-{MARKER}-{_uid()[:6]}",
        project_sales_order_id=pso.id, state=INQUIRY_ACTIONED, raised_by=uploader,
        raised_at=raised_at,
    )
    db.add(inquiry)
    db.flush()
    actioned_at = raised_at if actioned_offset is None else raised_at + actioned_offset
    row = OrderInquiryRow(
        id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id, so_line_id=mirror.id,
        item_code=f"{MARKER}-ITEM", qty=Decimal(qty), delivery_date=delivery_date, verb=verb,
        state=INQUIRY_ACTIONED,
        actioned_by=actioned_by if actioned_by is not None else uploader,
        actioned_at=actioned_at,
    )
    db.add(row)
    db.flush()
    return {
        "so_number": so_number, "pso": pso, "core_line": core_line, "inquiry": inquiry,
        "row": row,
    }


def test_ac_ou_10_main_refuses_without_delivery_from():
    """AC-OU-10. `--delivery-from` is mandatory; `main()` exits 2 without it, before
    touching the database at all."""
    with pytest.raises(SystemExit) as exc_info:
        reopen.main([])
    assert exc_info.value.code == 2


def test_ac_ou_11a_an_importer_closed_row_on_or_after_the_cutoff_reopens():
    """AC-OU-11. An importer-closed ORDER row with delivery 15 Sep and `--delivery-from
    2026-09-01 --apply` becomes `raised`, `actioned_by`/`actioned_at` NULL, header back
    to `raised`."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        world = _reopen_candidate(db, company_id, uploader, delivery_date=date(2026, 9, 15))
        db.commit()

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()

        matches = [r for r in result if r.get("qty") == Decimal("3")
                   and r.get("delivery_date") == date(2026, 9, 15)]
        assert matches, result
        assert matches[0]["action"] == "reopened", result

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_RAISED
        assert world["row"].actioned_by is None
        assert world["row"].actioned_at is None
        db.refresh(world["inquiry"])
        assert world["inquiry"].state == INQUIRY_RAISED


def test_ac_ou_11b_delivery_before_the_cutoff_is_untouched():
    """AC-OU-11. A row with delivery 15 Aug is skipped (`skipped_before_from`) when the
    cutoff is 1 Sep, and the row itself is never touched."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        world = _reopen_candidate(db, company_id, uploader, delivery_date=date(2026, 8, 15))
        db.commit()

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()

        matches = [r for r in result if r.get("delivery_date") == date(2026, 8, 15)]
        assert matches, result
        assert matches[0]["action"] == "skipped_before_from", result

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_ACTIONED, "a row before the cutoff must be untouched"
        assert world["row"].actioned_by == uploader


def test_ac_ou_11c_a_person_actioned_row_is_never_touched():
    """AC-OU-11. A row a PERSON marked actioned (`actioned_at` well outside the
    importer's own clock window) is never reopened, even on or after the cutoff."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        world = _reopen_candidate(
            db, company_id, uploader, delivery_date=date(2026, 9, 15),
            actioned_offset=timedelta(hours=3),
        )
        db.commit()

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()

        matches = [r for r in result if r.get("delivery_date") == date(2026, 9, 15)]
        assert matches, result
        assert matches[0]["action"] == "skipped_person_actioned", result

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_ACTIONED, "a person's own action must never flip"
        assert world["row"].actioned_by == uploader


def test_ac_ou_11d_a_cancelled_core_line_is_never_touched():
    """AC-OU-11. A candidate whose core line is CANCELLED (not merely delivered/closed)
    is skipped (`skipped_cancelled_line`) and never reopened."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        world = _reopen_candidate(
            db, company_id, uploader, delivery_date=date(2026, 9, 15),
            line_status="cancelled",
        )
        db.commit()

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()

        matches = [r for r in result if r.get("delivery_date") == date(2026, 9, 15)]
        assert matches, result
        assert matches[0]["action"] == "skipped_cancelled_line", result

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_ACTIONED
        assert world["row"].actioned_by == uploader


def test_ac_ou_11f_the_principal_guard_same_instant_different_actor_is_skipped():
    """AC-OU-11, the principal half of the two-signal importer-closed test (module
    docstring; the same test `backfill_order_back_rows.py::_is_importer_closed` uses,
    R3/R4 precedent). `actioned_at` sits in the SAME instant as the header's own
    `raised_at` - the CLOCK signal alone would call this importer-closed - but
    `actioned_by` is a DIFFERENT principal from the header's own `raised_by`: a
    purchasing user who happened to mark the row actioned in the same second the sheet
    raised it. Never reopened."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        purchasing_user = _uploader(db)
        world = _reopen_candidate(
            db, company_id, uploader, delivery_date=date(2026, 9, 15),
            actioned_by=purchasing_user,
        )
        db.commit()

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()

        matches = [r for r in result if r.get("delivery_date") == date(2026, 9, 15)]
        assert matches, result
        assert matches[0]["action"] == "skipped_person_actioned", (
            "the CLOCK alone matched, but the PRINCIPAL differs from the header's own "
            "raised_by - a different actor's same-instant action must never flip"
        )

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_ACTIONED
        assert world["row"].actioned_by == purchasing_user


def test_ac_ou_11g_company_code_scopes_the_reopen_to_one_company():
    """AC-OU-11, `--company` scoping (module docstring, `company_code`). The SAME SO
    number exists in TWO companies (`so_number` is unique per company, not globally -
    `uq_sales_orders_company_so_number`), each carrying an otherwise-identical
    importer-closed candidate. `company_code='SRT'` reopens only SRT's row; the OTHER
    company's identically-numbered row is untouched."""
    with pg_session() as db:
        sorento_id = _sorento(db)
        other_id = _uid()
        db.execute(text(
            "INSERT INTO companies (id, name, code, is_active, created_at) "
            "VALUES (:i, :n, :c, true, now())"
        ), {"i": other_id, "n": f"{MARKER} Other Co", "c": f"{MARKER}-CO-{other_id[:6]}"})
        db.flush()

        shared_so = f"{MARKER}-SO-SHARED-{_uid()[:6]}"
        sorento_uploader = _uploader(db)
        other_uploader = _uploader(db)
        sorento_world = _reopen_candidate(
            db, sorento_id, sorento_uploader, so_number=shared_so,
            delivery_date=date(2026, 9, 15),
        )
        other_world = _reopen_candidate(
            db, other_id, other_uploader, so_number=shared_so,
            delivery_date=date(2026, 9, 15),
        )
        db.commit()

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code="SRT", apply=True,
        )
        db.commit()

        matches = [r for r in result if r.get("so_number") == shared_so]
        assert matches, result
        assert all(r.get("company_code") == "SRT" for r in matches), (
            "a company_code filter must never report a row from a DIFFERENT company", result,
        )

        db.refresh(sorento_world["row"])
        assert sorento_world["row"].state == INQUIRY_RAISED, "SRT's own row must reopen"

        db.refresh(other_world["row"])
        assert other_world["row"].state == INQUIRY_ACTIONED, (
            "the OTHER company's identically-numbered row must be untouched"
        )
        assert other_world["row"].actioned_by == other_uploader


def test_ac_ou_11h_a_second_apply_run_is_idempotent():
    """AC-OU-11, idempotence (module docstring, SAFETY / IDEMPOTENCY, the same guarantee
    `backfill_order_back_rows.py` gives). Running `apply=True` a SECOND time over rows
    the first run already reopened finds nothing left to flip - the candidate query is
    `state = 'actioned'`, and a reopened row now reads `raised` - so no `reopened`
    action appears and the row's state is unchanged by the second run."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        world = _reopen_candidate(db, company_id, uploader, delivery_date=date(2026, 9, 15))
        db.commit()

        first = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()
        first_matches = [r for r in first if r.get("delivery_date") == date(2026, 9, 15)]
        assert first_matches and first_matches[0]["action"] == "reopened", first

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_RAISED

        second = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=True,
        )
        db.commit()

        second_matches = [r for r in second if r.get("delivery_date") == date(2026, 9, 15)]
        assert second_matches == [], (
            "a row the first run already reopened is no longer `state = actioned`, so "
            "the second run's own candidate query must never pick it up at all", second,
        )

        db.refresh(world["row"])
        assert world["row"].state == INQUIRY_RAISED, "the second run must change nothing"


def test_ac_ou_11e_a_dry_run_writes_nothing_but_still_prints_the_candidate():
    """AC-OU-11. The default (`apply=False`) reports the same candidate list as an
    `apply` run would, and writes nothing at all.

    Deliberately NO `db.commit()` before calling `run()` here, unlike its apply=True
    siblings below: `run()` reads through the SAME session `db` is bound to, so the
    seed's own `.flush()` calls (inside `_reopen_candidate`) are already visible to it
    within the one open transaction - a dry run never commits internally either
    (`if apply: db.commit()`, same shape `backfill_order_back_rows.py::run` uses), so
    this test is the one case in the file where `pg_session`'s own rollback at teardown
    genuinely undoes everything and no ZZT-REOP row is left committed."""
    with pg_session() as db:
        company_id = _sorento(db)
        uploader = _uploader(db)
        world = _reopen_candidate(db, company_id, uploader, delivery_date=date(2026, 9, 15))
        expected_actioned_at = world["row"].actioned_at

        result = reopen.run(
            db, delivery_from=date(2026, 9, 1), company_code=None, apply=False,
        )

        matches = [r for r in result if r.get("delivery_date") == date(2026, 9, 15)]
        assert matches, result
        assert matches[0]["action"] == "reopened", (
            "a dry run still CLASSIFIES the candidate as one that would reopen"
        )

        db.expire_all()
        row = db.get(OrderInquiryRow, world["row"].id)
        assert row.state == INQUIRY_ACTIONED, "a dry run must write nothing"
        assert row.actioned_at == expected_actioned_at
        inquiry = db.get(OrderInquiry, world["inquiry"].id)
        assert inquiry.state == INQUIRY_ACTIONED
