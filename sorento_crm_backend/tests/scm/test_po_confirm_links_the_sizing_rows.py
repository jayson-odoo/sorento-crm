"""P7: confirming a purchase order links the rows that SIZED it, before anybody else.

`PLAN-scm-purchasing-uat-journey.md` P7. A purchase order raised off the plan is a buy for
particular plan ROWS, and a plan row is a `(product, location)` cell whose Project figure is
the un-linked remainder of the Order Inquiry rows sitting at it. The cascade on its own
walks the earliest open row by date across the WHOLE product, so a confirm could satisfy a
row at the other end of the country while the row that asked for the buy stayed raised and
the PO's "Allocated to" panel named a stranger.

The case is the captain's own: a plan row sized by two raised rows (5 + 3) against a PO line
of 8, with an OLDER raised row for the same product at a different warehouse. Two passes
must give the 8 to the two rows that sized it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import text

from app.services.scm.purchase_order_service import PurchaseOrderService
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, seed_user
from tests.scm.test_channel_read_model import _confirmed_leg
from tests.scm.test_m3_run import _mk_product, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTP7"


def _u() -> str:
    return str(uuid.uuid4())


def _linked_qty(db, row_id) -> float:
    return float(db.execute(text(
        "SELECT COALESCE(SUM(qty), 0) FROM projects.order_inquiry_links WHERE row_id = :r"
    ), {"r": row_id}).scalar() or 0)


def test_the_confirm_links_the_two_rows_that_sized_the_line_not_the_older_one(scm_app):
    """POOL locations - codes with no `-<group>` suffix - and that is deliberate.

    Ladder v4 section 1d refuses a GROUP-location purchase-order line to the cascade
    unless `group_net + the group's own open PO balance > 0`, and a purchase order raised
    off the plan to cover exactly the plan's Project figure lands on zero: the backlog it
    is sized against is the very demand it would be linked to. That rule is about which
    LINES may be offered and this test is about which ROWS get them, so the scenario is
    put where only one rule is in play. `group_of_warehouse_code` reads the suffix after
    the first hyphen, so a code with no hyphen carries no group at all.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _mk_warehouse(db, f"{MARKER}HERE")
    elsewhere = _mk_warehouse(db, f"{MARKER}AWAY")
    pid = _mk_product(db, f"{MARKER}-SKU")

    # OLDEST first, so the plain cascade would reach for it before either of the two below.
    older = _confirmed_leg(db, product_id=pid, warehouse_id=elsewhere, buy_qty=9)
    five = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    three = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=3)

    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
        "'scm_recommendation')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
        "VALUES (:i, :po, :p, :w, 8, 0, 10, 'MYR', 'open')"),
        {"i": _u(), "po": poid, "p": pid, "w": here})
    db.flush()

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, five["inquiry_row"].id) == 5.0
    assert _linked_qty(db, three["inquiry_row"].id) == 3.0
    assert _linked_qty(db, older["inquiry_row"].id) == 0.0, (
        "the older row at another warehouse took the buy the two rows at this one sized"
    )


def test_a_product_with_a_located_and_an_unlocated_line_does_not_kill_the_cascade(scm_app):
    """The `sorted(cells)` trap. Cells are `(product_id, warehouse_id | None)`, and a bare
    sort compares element by element - one line of a product with a warehouse and another
    without gives `str < None`, a TypeError, INSIDE the best-effort try. The whole cascade
    would be skipped and one log line left behind, which is the worst shape a defect can
    take: a confirm that reports success and links nothing.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _mk_warehouse(db, f"{MARKER}-MIXED")
    pid = _mk_product(db, f"{MARKER}-MIXSKU")
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=4)

    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
        "'scm_recommendation')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    for warehouse in (here, None):
        db.execute(text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
            "VALUES (:i, :po, :p, :w, 4, 0, 10, 'MYR', 'open')"),
            {"i": _u(), "po": poid, "p": pid, "w": warehouse})
    db.flush()

    out = PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert out["confirmed_count"] == 1
    assert _linked_qty(db, row["inquiry_row"].id) == 4.0, (
        "the cascade was skipped, which is what the TypeError did silently"
    )


def test_rows_needed_at_reads_the_location_the_view_reads(scm_app):
    """The helper on its own: a row lands at the reconciled core line's warehouse, and a
    cell naming a DIFFERENT warehouse must not claim it."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    _, db, _, _ = scm_app
    here = _mk_warehouse(db, f"{MARKER}-NEEDA")
    elsewhere = _mk_warehouse(db, f"{MARKER}-NEEDB")
    pid = _mk_product(db, f"{MARKER}-NEEDSKU")
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=6)
    db.flush()

    service = ProjectOrderInquiryService(db)

    assert str(row["inquiry_row"].id) in service.rows_needed_at([(pid, here)])
    assert str(row["inquiry_row"].id) not in service.rows_needed_at([(pid, elsewhere)])
    assert service.rows_needed_at([(pid, None)]) == [], "a NULL cell claims a located row"
    assert service.rows_needed_at([]) == []


# ---------------------------------------------------------------------------
# The link horizon on a purchase-order confirm (`PLAN-scm-oi-handshake.md` section 11)
# ---------------------------------------------------------------------------


def _plan_run(db, when, *, finished_at=None) -> str:
    """One COMPLETED reorder run, at a "Plan until" date.

    The plan run - not `scm.priority_policy.reorder_coverage_until` (S2, code review
    27 Aug 2026). That policy field is the ladder's BUY-NOW line: a row needed AFTER it is
    the row the engine proposes buying, so reading it as the link horizon meant the
    purchase order raised for those rows could never be linked back to them.
    """
    run_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_run (id, company_id, status, plan_horizon_date, "
        "started_at, finished_at, created_at) "
        "VALUES (:i, :c, 'completed', :h, :f, :f, :f)"),
        {"i": run_id, "c": SORENTO_COMPANY_ID, "h": when,
         "f": finished_at or datetime(2026, 8, 20, 9, 0, 0)})
    db.flush()
    return run_id


def _rec_of(db, run_id: str, product_id: str) -> str:
    """The recommendation a draft PO line names in its `source_ref` - the ONE thread back
    from a confirmed buy to the run that sized it."""
    rec_id = _u()
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation (id, company_id, run_id, rec_type, "
        "product_id) VALUES (:i, :c, :r, 'buy', :p)"),
        {"i": rec_id, "c": SORENTO_COMPANY_ID, "r": run_id, "p": product_id})
    db.flush()
    return rec_id


def _draft_po(db, *, product_id, warehouse_id, qty, source_ref=None) -> str:
    """A `draft_recommendation` purchase order of one line, optionally threaded back to
    the recommendation (and therefore the run) it was drafted off."""
    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
        "'scm_recommendation')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status, "
        "source_system, source_ref) "
        "VALUES (:i, :po, :p, :w, :q, 0, 10, 'MYR', 'open', :ss, :sr)"),
        {"i": _u(), "po": poid, "p": product_id, "w": warehouse_id, "q": qty,
         "ss": "scm_recommendation" if source_ref else None, "sr": source_ref})
    db.flush()
    return poid


def test_a_confirm_leaves_a_row_due_beyond_the_plans_horizon_unlinked(scm_app):
    """A confirm has nobody to ask for a date, so it uses the plan's own - the horizon the
    buy was sized against. A 2030 line eating the purchase order a 2026 line asked for is
    the whole reason the date exists."""
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _mk_warehouse(db, f"{MARKER}HZN")
    pid = _mk_product(db, f"{MARKER}-HZNSKU")
    run = _plan_run(db, date(2026, 12, 31))

    near = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    far = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=3)
    near["inquiry_row"].delivery_date = date(2026, 10, 1)
    far["inquiry_row"].delivery_date = date(2030, 1, 1)
    db.flush()

    poid = _draft_po(db, product_id=pid, warehouse_id=here, qty=8,
                     source_ref=_rec_of(db, run, pid))

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, near["inquiry_row"].id) == 5.0
    assert _linked_qty(db, far["inquiry_row"].id) == 0.0, (
        "the 2030 row took the buy under a horizon that does not reach it"
    )


def test_a_confirm_links_under_the_horizon_of_the_run_it_was_drafted_off(scm_app):
    """S2 (code review, 27 Aug 2026): ITS run, not the newest one.

    A draft purchase order is a buy sized by one particular plan run, and it may sit in
    the drafts for days while another run plans further out. Linking it under the newer
    run's horizon would hand the buy to rows the run that ordered it never counted.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _mk_warehouse(db, f"{MARKER}OWNRUN")
    pid = _mk_product(db, f"{MARKER}-OWNRUNSKU")
    own = _plan_run(db, date(2026, 12, 31), finished_at=datetime(2026, 8, 20, 9, 0, 0))
    _plan_run(db, date(2030, 12, 31), finished_at=datetime(2026, 8, 26, 9, 0, 0))

    near = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    far = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=3)
    near["inquiry_row"].delivery_date = date(2026, 10, 1)
    far["inquiry_row"].delivery_date = date(2030, 1, 1)
    db.flush()

    poid = _draft_po(db, product_id=pid, warehouse_id=here, qty=8,
                     source_ref=_rec_of(db, own, pid))

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, near["inquiry_row"].id) == 5.0
    assert _linked_qty(db, far["inquiry_row"].id) == 0.0, (
        "the buy was linked under a horizon a LATER run planned to"
    )


# ---------------------------------------------------------------------------
# `_groups_in_deficit`: the boundary (captain, 27 Aug)
# ---------------------------------------------------------------------------


def _group_warehouse(db, code: str) -> str:
    """A warehouse whose code carries an ownership-group suffix, so ladder v4's group rule
    is in play (`group_of_warehouse_code` reads the suffix after the first hyphen)."""
    return _mk_warehouse(db, code)


def test_a_group_bought_to_exactly_the_plan_figure_is_still_offered(scm_app):
    """The boundary, and it is the ordinary case rather than an edge one.

    A purchase order raised off the plan buys exactly what the plan said was short, so the
    group lands on `group_net + remaining == 0`. Read as "at or below zero is deficit" that
    group is refused its own purchase order and the rows that sized it stay raised forever -
    the buy is invisible to the cascade, to the PO-confirm pass and to the Link dialog.
    Offered at zero: nothing is promised twice, because the demand this covers IS the
    demand the group carries.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _group_warehouse(db, f"{MARKER}EXACT-BB")
    pid = _mk_product(db, f"{MARKER}-EXACTSKU")
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=8)

    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
        "'scm_recommendation')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
        "VALUES (:i, :po, :p, :w, 8, 0, 10, 'MYR', 'open')"),
        {"i": _u(), "po": poid, "p": pid, "w": here})
    db.flush()

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, row["inquiry_row"].id) == 8.0, (
        "a group bought to exactly the plan figure was refused its own purchase order"
    )


def test_a_group_short_of_its_backlog_is_offered_for_an_acknowledged_unlinked_row(scm_app):
    """The second half of the ruling. The group is genuinely short - it owes more than its
    open purchase orders can cover - but it holds an ACKNOWLEDGED row nobody has linked,
    and that row is the demand somebody bought this purchase order for. Refusing it would
    leave a buy sitting open beside the instruction it answers.
    """
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _group_warehouse(db, f"{MARKER}SHORT-BB")
    pid = _mk_product(db, f"{MARKER}-SHORTSKU")
    # 13 owed at the group against 8 on order: net + remaining is -5, a real deficit.
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=8)
    _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)

    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'active', :d, 'MYR', 'autocount')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
        "VALUES (:i, :po, :p, :w, 8, 0, 10, 'MYR', 'open')"),
        {"i": _u(), "po": poid, "p": pid, "w": here})
    db.flush()

    ProjectOrderInquiryService(db).auto_place_for_products(
        [pid], actor_user_id=actor, trigger="worklist",
    )

    assert _linked_qty(db, row["inquiry_row"].id) > 0, (
        "the group's own acknowledged row was refused the purchase order bought for it"
    )
