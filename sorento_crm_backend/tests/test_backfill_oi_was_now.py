"""The one-off backfill for #992's own gap: rows written BEFORE that deploy.

PR #992 made a confirm that releases a received row (`redirected_to_pool = true`, "used")
stamp the fresh ORDER row it raises with `previous_qty` / `previous_delivery_date` and a
"Replaces <qty> used; ..." note, and cancel the DELAY/ADVANCE reaction row beside it. Rows
raised before that deploy carry the used row's own "released at revision N" note but never
got either half of that. This suite pins the backfill script that repairs them after the
fact, on the real database through `pg_session` (rolled back), the same substrate
`test_backfill_retire_superseded_order_inquiry_rows.py` uses for the same reason: sqlite
cannot host the `projects` schema at all.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.base import set_company_scope
from app.models.project_so import (
    DECISION_SUPERSEDED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_RAISED,
    IV_DELAY,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SO_STATUS_PUBLISHED,
    SOSupplyDecision,
)
from app.models.projects import Project
from tests._pg_fixture import pg_session

import scripts.backfill_oi_was_now as backfill

MARKER = "ZZTOIBF"
SORENTO = "00000000-0000-0000-0000-000000000001"

REVISION_NO = 7
USED_QTY = Decimal("158")
USED_DATE = date(2026, 8, 1)
FRESH_QTY = Decimal("220")
FRESH_DATE = date(2027, 3, 1)


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as session:
        # The script has no request and no principal, so it runs all-companies. Mirror it
        # here or the test proves something the script never does.
        set_company_scope(session, None)
        yield session


@pytest.fixture()
def world(db):
    """One SO line carrying a used row (released at revision 7) and the fresh ORDER row
    #992 would have stamped had it existed then - plus the DELAY row #992 would have
    cancelled beside it."""
    project = Project(
        id=_u(), company_id=SORENTO, project_code=f"{MARKER}-P-{uuid.uuid4().hex[:6]}",
        title=f"{MARKER} Tower", normalised_title=f"{MARKER.lower()} {uuid.uuid4().hex[:6]}",
    )
    db.add(project)
    db.flush()
    pso = ProjectSalesOrder(
        id=_u(), company_id=SORENTO, project_id=project.id,
        provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        autocount_doc_no=f"{MARKER}-SO900001",
        status=SO_STATUS_PUBLISHED, published_at=datetime.utcnow(), grouping_origin="area",
    )
    db.add(pso)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_u(), company_id=SORENTO, project_sales_order_id=pso.id, line_no=1,
        qty=FRESH_QTY, delivery_date=FRESH_DATE,
    )
    db.add(line)
    db.flush()
    inquiry = OrderInquiry(
        id=_u(), company_id=SORENTO, inquiry_no=f"{MARKER}-{uuid.uuid4().hex[:8]}"[:20],
        project_sales_order_id=pso.id, state=INQUIRY_RAISED,
    )
    db.add(inquiry)
    db.flush()
    decision = SOSupplyDecision(
        id=_u(), company_id=SORENTO, project_sales_order_id=pso.id, revision_no=REVISION_NO,
        line_snapshots={},
    )
    db.add(decision)
    db.flush()
    return {
        "db": db, "project": project, "pso": pso, "line": line, "inquiry": inquiry,
        "decision": decision,
    }


def _used_row(world, *, revision_no=REVISION_NO, note=None) -> OrderInquiryRow:
    db = world["db"]
    row = OrderInquiryRow(
        id=_u(), company_id=SORENTO, order_inquiry_id=world["inquiry"].id,
        so_line_id=world["line"].id, item_code=f"{MARKER}-ITEM", qty=USED_QTY,
        delivery_date=USED_DATE, stock_location="MAIN", verb=IV_ORDER,
        state=INQUIRY_PARTLY_LINKED, redirected_to_pool=True,
        note=note if note is not None else (
            f"{MARKER}-PO-9001 received 12 Aug 2026, goods are MAIN stock, "
            f"released at revision {revision_no}"
        ),
    )
    db.add(row)
    db.flush()
    return row


def _fresh_row(
    world, *, supply_decision_id=None, previous_qty=None, state=INQUIRY_RAISED
) -> OrderInquiryRow:
    db = world["db"]
    row = OrderInquiryRow(
        id=_u(), company_id=SORENTO, order_inquiry_id=world["inquiry"].id,
        so_line_id=world["line"].id, item_code=f"{MARKER}-ITEM", qty=FRESH_QTY,
        delivery_date=FRESH_DATE, verb=IV_ORDER, state=state,
        supply_decision_id=(
            world["decision"].id if supply_decision_id is None else supply_decision_id
        ),
        previous_qty=previous_qty,
    )
    db.add(row)
    db.flush()
    return row


def _delay_row(world, *, created_at=None) -> OrderInquiryRow:
    db = world["db"]
    row = OrderInquiryRow(
        id=_u(), company_id=SORENTO, order_inquiry_id=world["inquiry"].id,
        so_line_id=world["line"].id, item_code=f"{MARKER}-ITEM", qty=Decimal("0"),
        delivery_date=FRESH_DATE, verb=IV_DELAY, state=INQUIRY_RAISED,
        supply_decision_id=None, note="Was 2026-06-01",
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return row


def test_dry_run_changes_nothing(world):
    used = _used_row(world)
    fresh = _fresh_row(world)
    delay = _delay_row(world)

    summary = backfill.run(world["db"], apply=False)

    assert summary["fresh_rows_found"] == 1
    assert summary["fresh_rows_stamped"] == 0
    world["db"].refresh(fresh)
    world["db"].refresh(delay)
    assert fresh.previous_qty is None
    assert fresh.note is None
    assert delay.state == INQUIRY_RAISED
    assert delay.note == "Was 2026-06-01"
    # nothing about the used row itself changes either
    world["db"].refresh(used)
    assert used.redirected_to_pool is True


def test_apply_stamps_fresh_row_and_cancels_delay_row(world):
    used = _used_row(world)
    fresh = _fresh_row(world)
    delay = _delay_row(world)

    summary = backfill.run(world["db"], apply=True)

    assert summary["fresh_rows_stamped"] == 1
    assert summary["reaction_rows_cancelled"] == 1

    world["db"].refresh(fresh)
    assert fresh.previous_qty == USED_QTY
    assert fresh.previous_delivery_date == USED_DATE
    assert fresh.note is not None
    assert f"Replaces {USED_QTY.normalize():f} used" in fresh.note

    world["db"].refresh(delay)
    assert delay.state == INQUIRY_CANCELLED
    assert f"Superseded by revision {REVISION_NO}" in delay.note
    assert "backfill 18 Sep 2026" in delay.note
    assert delay.note.startswith("Was 2026-06-01"), "the delay row's own note is kept, not replaced"


def test_second_apply_is_a_no_op(world):
    _used_row(world)
    fresh = _fresh_row(world)
    delay = _delay_row(world)

    backfill.run(world["db"], apply=True)
    note_after_first = fresh.note

    summary = backfill.run(world["db"], apply=True)

    assert summary["fresh_rows_found"] == 0
    assert summary["fresh_rows_stamped"] == 0
    assert summary["reaction_rows_cancelled"] == 0
    world["db"].refresh(fresh)
    world["db"].refresh(delay)
    assert fresh.note == note_after_first, "the note was appended to a second time"
    assert delay.state == INQUIRY_CANCELLED


def test_used_row_with_no_fresh_row_is_skipped(world):
    """AC (d): a used row naming a revision this order never raised a fresh row under -
    nothing crashes, nothing is written."""
    used = _used_row(world)
    # No fresh row at all for revision 7 on this line.

    summary = backfill.run(world["db"], apply=True)

    assert summary["fresh_rows_found"] == 0
    assert summary["fresh_rows_stamped"] == 0
    world["db"].refresh(used)
    assert used.redirected_to_pool is True
    assert "released at revision" in used.note


def test_used_row_with_no_revision_fragment_is_skipped(world):
    """A used row that was never released through `_redirect_row_if_received` at all -
    no revision to look a fresh row up by."""
    _used_row(world, note="some other note entirely")
    _fresh_row(world)

    summary = backfill.run(world["db"], apply=True)

    assert summary["fresh_rows_found"] == 0


def test_reconfirm_that_supersedes_revision_n_still_stamps_the_live_row(world):
    """Owner correction, 18 Sep 2026 (SO314593/SO314594 on prod): a network-outage
    reconfirm can supersede revision N's OWN fresh row before this ever runs - CS
    reconfirmed at revision N+1 minutes later, cancelling the row revision N raised and
    raising a fresh one under the new decision instead. The live 220 sits on revision
    N+1's row, and the DELAY row the FIRST confirm raised is still cancelled - keyed off
    revision N's own `confirmed_at` (10:11), never the live row's much later
    `created_at` (11:25)."""
    db = world["db"]
    t1 = datetime(2026, 9, 16, 10, 11, 0)
    t2 = datetime(2026, 9, 16, 11, 25, 0)
    world["decision"].confirmed_at = t1
    world["decision"].state = DECISION_SUPERSEDED
    db.flush()

    _used_row(world)  # "released at revision 7"
    # Revision 7's OWN fresh row - already cancelled by CS's revision 8 reconfirm, and
    # must never be the one this backfill touches.
    stale_fresh = _fresh_row(world, state=INQUIRY_CANCELLED)

    decision2 = SOSupplyDecision(
        id=_u(), company_id=SORENTO, project_sales_order_id=world["pso"].id,
        revision_no=REVISION_NO + 1, confirmed_at=t2, line_snapshots={},
    )
    db.add(decision2)
    db.flush()
    live_fresh = _fresh_row(world, supply_decision_id=decision2.id)

    # Raised beside the FIRST confirm (revision 7, 10:11), not the reconfirm.
    delay = _delay_row(world, created_at=t1 + timedelta(minutes=1))

    summary = backfill.run(db, apply=True)

    assert summary["fresh_rows_stamped"] == 1
    assert summary["reaction_rows_cancelled"] == 1

    db.refresh(live_fresh)
    assert live_fresh.previous_qty == USED_QTY
    assert live_fresh.previous_delivery_date == USED_DATE
    assert f"Replaces {USED_QTY.normalize():f} used" in (live_fresh.note or "")

    db.refresh(stale_fresh)
    assert stale_fresh.previous_qty is None, "the cancelled revision-7 row must never be touched"

    db.refresh(delay)
    assert delay.state == INQUIRY_CANCELLED
    assert f"Superseded by revision {REVISION_NO}" in delay.note


def test_chain_with_no_live_row_anywhere_is_skipped(world):
    """The whole supersession chain has been walked and nothing on it is still a live,
    unstamped ORDER/ORDER_BACK row - nothing crashes, nothing is written."""
    db = world["db"]
    used = _used_row(world)
    world["decision"].state = DECISION_SUPERSEDED
    # Revision 7's own fresh row was cancelled by the reconfirm...
    _fresh_row(world, state=INQUIRY_CANCELLED)
    # ...and revision 8 (the reconfirm) raised nothing further on this line at all.
    decision2 = SOSupplyDecision(
        id=_u(), company_id=SORENTO, project_sales_order_id=world["pso"].id,
        revision_no=REVISION_NO + 1, line_snapshots={},
    )
    db.add(decision2)
    db.flush()

    summary = backfill.run(db, apply=True)

    assert summary["fresh_rows_found"] == 0
    assert summary["fresh_rows_stamped"] == 0
    db.refresh(used)
    assert used.redirected_to_pool is True
