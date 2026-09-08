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


def _pool_warehouse(db, code: str) -> str:
    """A warehouse that is genuinely a POOL by the FK `_pool_codes()` reads (slice H, 8 Sep
    2026 - the automatic pass takes from the site pool alone). None of this file's tests are
    about location FIT - they are about which of several ROWS a confirm's cascade serves, and
    about the reorder-run horizon - so the destination just has to be one the automatic pass
    may actually take from, or every assertion here would prove AC-H1 instead of what the
    test names."""
    warehouse_id = _mk_warehouse(db, code)
    _mk_warehouse(db, f"{code}-SIB", pool_warehouse_id=warehouse_id)
    return warehouse_id


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
    here = _pool_warehouse(db, f"{MARKER}HERE")
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
    here = _pool_warehouse(db, f"{MARKER}-MIXED")
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
    here = _pool_warehouse(db, f"{MARKER}HZN")
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
    here = _pool_warehouse(db, f"{MARKER}OWNRUN")
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


def test_a_confirm_off_a_run_that_named_no_horizon_links_under_none(scm_app):
    """The own run's horizon is NULL, and NULL is an answer (item 1, re-review 27 Aug).

    `plan_link_horizon` reads a named run's `plan_horizon_date` as it stands, so a run that
    planned every open line answers `None` - and `None` handed on as a bare date was
    indistinguishable from "this caller named nothing", which the cascade resolves by
    reaching for the LATEST completed run. The daily scheduled run names no horizon at all,
    so every purchase order drafted off it was linked under whatever date somebody's last
    manual run happened to plan to. A purchase order drafted off a run links under THAT
    run's horizon or under none.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _pool_warehouse(db, f"{MARKER}NOHZN")
    pid = _mk_product(db, f"{MARKER}-NOHZNSKU")
    own = _plan_run(db, None, finished_at=datetime(2026, 8, 20, 9, 0, 0))
    _plan_run(db, date(2026, 12, 31), finished_at=datetime(2099, 1, 1))

    near = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    far = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=3)
    near["inquiry_row"].delivery_date = date(2026, 10, 1)
    far["inquiry_row"].delivery_date = date(2030, 1, 1)
    db.flush()

    poid = _draft_po(db, product_id=pid, warehouse_id=here, qty=8,
                     source_ref=_rec_of(db, own, pid))

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, near["inquiry_row"].id) == 5.0
    assert _linked_qty(db, far["inquiry_row"].id) == 3.0, (
        "the run that sized this buy named no horizon, and a LATER run's date was used"
    )


def test_two_purchase_orders_confirmed_together_each_link_under_their_own_run(scm_app):
    """One press, two plans (item 2, re-review 27 Aug).

    The run was resolved ONCE for the whole batch, off every confirmed line's `source_ref`
    at once, and the lookup ended in `.limit(1)` with no ORDER BY - so which plan the batch
    linked under was whichever row Postgres handed back first, and the other purchase order
    was linked under a horizon its own run never planned to. Each purchase order is its own
    buy, sized by its own run.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    near_run = _plan_run(db, date(2026, 12, 31), finished_at=datetime(2026, 8, 20, 9, 0, 0))
    far_run = _plan_run(db, date(2031, 12, 31), finished_at=datetime(2026, 8, 21, 9, 0, 0))

    made = {}
    for name, run in (("NEAR", near_run), ("FAR", far_run)):
        warehouse = _pool_warehouse(db, f"{MARKER}BATCH{name}")
        pid = _mk_product(db, f"{MARKER}-BATCH{name}SKU")
        soon = _confirmed_leg(db, product_id=pid, warehouse_id=warehouse, buy_qty=5)
        late = _confirmed_leg(db, product_id=pid, warehouse_id=warehouse, buy_qty=3)
        soon["inquiry_row"].delivery_date = date(2026, 10, 1)
        late["inquiry_row"].delivery_date = date(2030, 1, 1)
        db.flush()
        made[name] = {
            "soon": soon["inquiry_row"].id,
            "late": late["inquiry_row"].id,
            "po": _draft_po(db, product_id=pid, warehouse_id=warehouse, qty=8,
                            source_ref=_rec_of(db, run, pid)),
        }

    PurchaseOrderService(db).bulk_confirm(
        [made["NEAR"]["po"], made["FAR"]["po"]], actor=actor
    )

    assert _linked_qty(db, made["NEAR"]["soon"]) == 5.0
    assert _linked_qty(db, made["NEAR"]["late"]) == 0.0, (
        "the 2030 row was linked under the OTHER purchase order's run, which plans to 2031"
    )
    assert _linked_qty(db, made["FAR"]["soon"]) == 5.0
    assert _linked_qty(db, made["FAR"]["late"]) == 3.0, (
        "the 2030 row was refused under the OTHER purchase order's run, which stops at 2026"
    )


def test_a_purchase_order_naming_two_runs_falls_back_to_the_latest_completed(scm_app):
    """A purchase order whose lines were drafted off two different plans names no ONE run,
    so it takes the plan in force - the same answer a hand-keyed purchase order gets - and
    says so in the log. Picking either of the two would be picking at random."""
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _pool_warehouse(db, f"{MARKER}TWORUNS")
    pid = _mk_product(db, f"{MARKER}-TWORUNSSKU")
    older = _plan_run(db, date(2026, 12, 31), finished_at=datetime(2026, 8, 20, 9, 0, 0))
    newer = _plan_run(db, date(2031, 12, 31), finished_at=datetime(2099, 1, 1))

    near = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    far = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=3)
    near["inquiry_row"].delivery_date = date(2026, 10, 1)
    far["inquiry_row"].delivery_date = date(2030, 1, 1)
    db.flush()

    poid = _draft_po(db, product_id=pid, warehouse_id=here, qty=5,
                     source_ref=_rec_of(db, older, pid))
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status, "
        "source_system, source_ref) "
        "VALUES (:i, :po, :p, :w, 3, 0, 10, 'MYR', 'open', 'scm_recommendation', :sr)"),
        {"i": _u(), "po": poid, "p": pid, "w": here,
         "sr": _rec_of(db, newer, pid)})
    db.flush()

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, near["inquiry_row"].id) == 5.0
    assert _linked_qty(db, far["inquiry_row"].id) == 3.0, (
        "two runs is no run: the plan in force reaches 2031 and the row is inside it"
    )

# ---------------------------------------------------------------------------
# `_groups_in_deficit`: the boundary (captain, 27 Aug)
# ---------------------------------------------------------------------------


def _group_warehouse(db, code: str) -> str:
    """A warehouse whose code carries an ownership-group suffix, so ladder v4's group rule
    is in play (`group_of_warehouse_code` reads the suffix after the first hyphen).

    `segment='project'` (B1, review of PR - the reviewer's own measurement against the
    7 Sep prod copy: 55 project-segment warehouses, 5 dealer-segment ones - the pools
    themselves - and zero null-segment. A bare group location is exactly a project bin on
    the real book, never an unclassified one, and leaving `segment` NULL here made
    `is_site_pool(None)` read True (`COALESCE(segment, 'dealer')`) - wrongly cascadable on
    its own account, a fixture artefact production has never had.
    """
    return _mk_warehouse(db, code, segment="project")


def test_a_group_bought_to_exactly_the_plan_figure_is_still_offered(scm_app):
    """The boundary, and it is the ordinary case rather than an edge one (captain, 27 Aug):
    a purchase order raised off the plan buys exactly what the plan said was short,
    landing the group on `group_net + remaining == 0` - offered, never refused, so the
    row that sized it is never stranded.

    B1 (review of PR, coordinator's own measurement against the 7 Sep prod copy): this IS
    AC-H11's scenario, not AC-H1's. `bulk_confirm` on a `draft_recommendation` PO calls
    `supply_claim.claim_purchase_order_for_sizing_rows`, which claims every PROJECT-BIN
    line of the confirmed order for the rows that sized its plan cell - the same
    `own_so_claim` `_candidate` now reads. A group location IS a project bin on the real
    book (`segment='project'`, measured; see `_group_warehouse`), so this row's own claim
    is written in the SAME transaction the confirm runs in, and the row links in full -
    exactly as it did before slice H, through the exception the owner explicitly kept.
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
        "AC-H11: a group bought to exactly the plan figure was refused its own purchase "
        "order - the write-time claim is the owner's own-SO exception, not gated on the "
        "deficit boundary at all"
    )


def test_a_group_short_of_its_backlog_is_still_never_auto_taken(scm_app):
    """The second half of the old ruling used to say the group's own acknowledged, unlinked
    row still reached its own purchase order however short the group's backlog was.

    B1 (review of PR): this PO is `autocount`-sourced and `active`, not a
    `draft_recommendation` this codebase confirmed, so `supply_claim.
    claim_purchase_order_for_sizing_rows` never runs and `own_so_claim` stays False - a
    genuinely different scenario from the sibling test above (which IS a plan confirm and
    DOES write the claim). The row stays raised because it is a `segment='project'` line
    nobody's SO claims (G12, AC-H1), not because the deficit boundary refuses it - the
    deficit boundary in fact LIFTS the refusal for this row (`_exempt_groups_for_row`),
    which is what the direct candidate-walk assertions below prove: without that lift
    (and without `_groups_in_deficit` excluding a STRANGER'S row from the same line), this
    test would pass for the wrong reason.
    """
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _group_warehouse(db, f"{MARKER}SHORT-BB")
    elsewhere = _group_warehouse(db, f"{MARKER}SHORT-CC")
    pid = _mk_product(db, f"{MARKER}-SHORTSKU")
    # 13 owed at the group against 8 on order: net + remaining is -5, a real deficit.
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=8)
    _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    # A DIFFERENT group's own acknowledged, unlinked row of the same product - its own
    # exemption is for ITS group ("CC"), never for "BB"'s.
    stranger = _confirmed_leg(db, product_id=pid, warehouse_id=elsewhere, buy_qty=3)

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

    service = ProjectOrderInquiryService(db)
    # AC-H10: `_groups_in_deficit` excludes group "BB"'s own line from a STRANGER row at
    # group "CC" entirely - nothing offered at all - while `_exempt_groups_for_row` lifts
    # that same exclusion for the row whose own acknowledged instruction the buy was
    # sized for. Deleting either function would make one of these two disagree with the
    # other: without `_groups_in_deficit`, the stranger would wrongly see the line too;
    # without `_exempt_groups_for_row`, the row that earned it would see nothing either.
    assert service._candidates_for_row(stranger["inquiry_row"]) == [], (
        "a stranger's row at a DIFFERENT group must not reach a line group BB's own "
        "backlog already owes"
    )
    offered = service._candidates_for_row(row["inquiry_row"])
    assert [c["location"] for c in offered] == [f"{MARKER}SHORT-BB"], (
        "the row that earned the exemption must still be OFFERED the line"
    )
    assert offered[0]["cascadable"] is False, (
        "AC-H1: offered is not cascadable - nobody's SO claims this project-bin line"
    )

    ProjectOrderInquiryService(db).auto_place_for_products(
        [pid], actor_user_id=actor, trigger="worklist",
    )

    assert _linked_qty(db, row["inquiry_row"].id) == 0.0, (
        "AC-H1: a project-bin line nobody's SO claims is never auto-taken, even for the "
        "row that earned the deficit exemption"
    )
