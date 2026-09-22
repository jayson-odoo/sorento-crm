"""Tests for `PLAN-reorder-plan-project-only.md` / its UAC (AC-PO-1..9; AC-PO-10 is the
existing-suite green check, run separately by the harness; AC-PO-11 is browser, skipped
here).

S1 (leg-2 admission dropped for `demand_class == "project"`) and S2 (a Project run sizes
a pool/single-location/product-grain buy on the confirmed project need ALONE, no retail
top-up) landed at `6123f358d`. Round 1 of this file was written test-first against
origin/main, before that commit, and most of it went green the moment the coder's
concurrent edits landed in the same worktree (see the commit message on this file's own
first commit for the record of what was genuinely red then). Round 2 (this pass, from
reviewer kill-test findings) adds the gaps that survived: the PROD SHAPE mutation kill
(the real prod policy row is `policy_type='reorder_level'`, so every product actually
sizes through `_emit_product`, never the `reorder_point` default every test up to here
ran on), a direct `_planning_rows` admission pin independent of any sizing branch, a
`_project_only_cell` mutation kill (the single-location fixture used to seed no forecast
demand, so the retail path coincidentally answered the same 20 the project-only path
does), exact-number pins on AC-PO-2/AC-PO-4 in place of loose `>0`/`!=20` assertions, and
a G10 "named product under a Project run keeps buyer intent" gap the coder has not yet
closed (`test_named_product_under_project_keeps_buyer_intent` stays genuinely red).

Every test below seeds a product that is BELOW ITS REORDER LEVEL (the leg-2 gate). Most
are POOLED across two dealer locations (so the pool-level buy in `_emit_pool` is computed
unconditionally of any one member's own committed demand - see the long G1 comment above
`_emit_cell` in `reorder_run_service.py`: a non-pooled, zero-committed cell emits nothing
at all, so a single-location fixture alone would not exercise the leg-2 admission bug this
lane fixes); the `_emit_product` twins use a single location instead, since that basis
plans the whole product regardless of pooling.

Harness copied from `tests/scm/test_m3_run.py` (`_client`, `_mk_*`) and
`tests/test_reorder_plan_demand_scope.py` (`_project_so_with_lines`, the confirmed-leg
ORDER-row builder already used to seed a real Order Inquiry chain: project + PSO +
inquiry + decision + row, one ACTIVE decision per PSO). Postgres only, via
`tests/scm/conftest.py::scm_app` - a live TestClient over a rolled-back SAVEPOINT. CI's
database starts empty: every test seeds its own full chain, nothing borrowed off the
shared local database.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import ACK_ACKNOWLEDGED, OrderInquiryLink
from app.models.scm import ReorderRun
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, scm_app  # noqa: F401
from tests.scm.test_m3_run import (
    _link,
    _mk_demand,
    _mk_movement,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)
from tests.test_reorder_plan_demand_scope import _project_so_with_lines

pytestmark = requires_pg

MARKER = "ZZTPO"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _recs_for(db, run_id: str, pid: str) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT rec_type, warehouse_id::text AS warehouse_id, rounded_qty, "
            "recommended_qty, triggered_reason AS reason_label, inputs "
            "FROM scm.reorder_recommendation WHERE run_id = :r AND product_id = :p"
        ),
        {"r": run_id, "p": pid},
    ).mappings().all()
    return [dict(r) for r in rows]


def _buy_rows(db, run_id: str, pid: str) -> list[dict]:
    return [r for r in _recs_for(db, run_id, pid) if r["rec_type"] == "buy"]


def _seed_pool_below_level(db, *, level=150, demand_add=5.0, lead=30, moq=1, mult=1):
    """Two pooled dealer locations, product-wide level `level`, on hand 0 at both, a
    recent movement (admits leg 2's "not dead" half), and a nonzero forecast demand rate
    at the root so the RETAIL policy genuinely fires - the fixture the plan's own measured
    facts describe (MPW800 level 150, on hand 0), widened to a pool so a zero-committed
    member's buy is not silently withheld by the unrelated G1 location-grain gate
    (`_emit_cell`'s `committed_here <= 0` withhold, which does not apply to a pool's own
    buy - see module docstring).
    """
    root_wid = _mk_warehouse(db, _code("ROOT"))
    child_wid = _mk_warehouse(db, _code("CHILD"), pool_warehouse_id=root_wid)
    pid = _mk_product(db, _code("P"))
    _mk_stock(db, pid, root_wid, 0)
    _mk_stock(db, pid, child_wid, 0)
    _mk_demand(db, pid, root_wid, demand_add)
    _mk_movement(db, pid, root_wid, 1, days_ago=7)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"), lead=lead, moq=moq, mult=mult)

    eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true WHERE scope_type = 'global'"))
    db.execute(
        text(
            "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
            "company_id, created_at) VALUES (:id, :p, NULL, :lvl, 'manual', :co, now())"
        ),
        {"id": _u(), "p": pid, "lvl": level, "co": SORENTO_COMPANY_ID},
    )
    db.flush()
    return {"pid": pid, "root_wid": root_wid, "child_wid": child_wid}


def _seed_single_below_level(db, *, level=150, lead=30, moq=1, mult=1, demand_add=5.0):
    """One dealer location, below its product-wide reorder level, on hand 0, a recent
    movement (leg 2's own admission gate) - the "with an ORDER row" fixtures (AC-PO-3..7,
    AC-PO-9): a single, non-pooled location whose committed demand is the ORDER row the
    caller adds.

    `demand_add` (nonzero by default - review round 2, mutation-kill for
    `_project_only_cell`) gives the location a real forecast: with NO forecast at all,
    `reorder_point`/`order_up_to` both resolve to 0, and the RETAIL sizing path
    coincidentally answers the SAME 20 the project-only path does (`net=-20`,
    `oup=0` -> `recommended = 0 - (-20) = 20`), so a test asserting `rounded_qty == 20`
    would pass whether or not `_emit_cell`'s `_project_only_cell` swap
    (`reorder_run_service.py` ~:1681) actually ran. With `demand_add=5.0` / `lead=30` the
    retail path instead answers 335 (`rop=185`, `oup=335`, `net=-20` ->
    `recommended=355`... rounded against `moq=1`/`mult=1` -> 355) - so a caller that seeds
    an ORDER row here and asserts `rounded_qty == 20` genuinely kills a coder who drops
    the project-only swap.
    """
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    _mk_stock(db, pid, wid, 0)
    _mk_movement(db, pid, wid, 1, days_ago=7)
    if demand_add:
        _mk_demand(db, pid, wid, demand_add)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"), lead=lead, moq=moq, mult=mult)

    eng.ensure_reorder_policy_defaults(db)
    db.execute(
        text(
            "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
            "company_id, created_at) VALUES (:id, :p, NULL, :lvl, 'manual', :co, now())"
        ),
        {"id": _u(), "p": pid, "lvl": level, "co": SORENTO_COMPANY_ID},
    )
    db.flush()
    return {"pid": pid, "wid": wid}


def _expected_pool_retail_buy(*, demand_add: float, lead: float, on_hand: float = 0.0) -> float:
    """Reproduces `eng.aggregate_network`'s pool-level sizing for `_seed_pool_below_level`'s
    own shape (on hand 0 at both members, forecast demand only at the root, moq=1/mult=1
    so no rounding moves the figure) via the SAME pure engine functions `_emit_pool` calls,
    rather than a hand-typed constant that could quietly drift from them (review round 2,
    item 4: AC-PO-2/AC-PO-4 assert the EXACT retail figure, not merely `> 0` / `!= 20`).
    """
    ss = demand_add * eng.DEFAULT_SAFETY_DAYS
    rop = eng.reorder_point(demand_add, lead, ss)
    oup = eng.order_up_to(rop, demand_add, eng.DEFAULT_REVIEW_PERIOD_DAYS)
    return oup - on_hand


def _use_reorder_level_policy(db) -> None:
    """The PROD SHAPE (review round 2, blocker): the 21 Sep prod copy carries ONE global
    `scm.reorder_policy` row, `policy_type='reorder_level'`, `pool_netting=false` - every
    product sizes through `_emit_product` (the product-grain reorder-level basis), never
    `_emit_pool` or the plain `_emit_cell` path every test above this point exercises
    (those all run on the ENGINE's own `reorder_point` default, which is not what prod
    actually has configured). Call AFTER `eng.ensure_reorder_policy_defaults(db)` has run
    (every `_seed_*_below_level` helper above already calls it) so this UPDATEs the row
    rather than racing its own idempotent INSERT.
    """
    db.execute(text("UPDATE scm.reorder_policy SET policy_type = 'reorder_level' WHERE scope_type = 'global'"))
    db.flush()


# ===========================================================================
# AC-PO-1 / AC-PO-2 - leg 2 (below reorder level) must not admit a Project run
# ===========================================================================

def test_ac_po_1_project_run_does_not_admit_a_below_level_product_with_no_project_row(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="project", so_numbers=[])
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"expected no recommendation at all, got {recs}"


def test_ac_po_2_dealer_run_still_admits_and_buys_the_same_product(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="retail", so_numbers=[])
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "a Dealer run must still buy for a below-level product"
    expected = _expected_pool_retail_buy(demand_add=5.0, lead=30)
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == expected, f"expected the pool's own retail figure ({expected}), got {total}"


def test_admission_leg2_dropped_for_project_but_kept_for_dealer(scm_app):
    """S1 pinned directly at `_planning_rows`, independent of any sizing branch (review
    round 2, item 2): reverting ONLY the project branch of `product_admit_join`
    (`reorder_run_service.py` ~:1032) back to the unconditional leg-1+leg-2 UNION makes
    this red even if every sizing branch below it still happened to emit nothing for a
    zero-committed product - the AC-PO-1/AC-PO-3.. tests above cannot tell "never admitted"
    apart from "admitted, then correctly sized to nothing" (`_emit_cell`'s own G1 gate
    already withholds a zero-committed cell's row for an unrelated reason). Same
    below-level, no-project-row seed as AC-PO-1; a Dealer ('retail') call is the same
    admission gate this lane leaves untouched, so it must still find the product.
    """
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)

    project_rows = svc._planning_rows(db, None, demand_class="project", so_numbers=[])
    dealer_rows = svc._planning_rows(db, None, demand_class="retail", so_numbers=[])

    project_pids = {str(r["product_id"]) for r in project_rows}
    dealer_pids = {str(r["product_id"]) for r in dealer_rows}
    assert u["pid"] not in project_pids, (
        "leg 2 (below reorder level) must not admit a Project run's universe at all"
    )
    assert u["pid"] in dealer_pids, "leg 2 must still admit a Dealer run's universe"


# ===========================================================================
# AC-PO-3 / AC-PO-4 - the project channel is sized ALONE, no retail top-up
# ===========================================================================

def test_ac_po_3_project_run_with_order_row_and_below_level_buys_exactly_the_order_qty(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    buys = [r for r in recs if r["rec_type"] == "buy"]
    # A pooled buy is emitted ONE ROW PER LOCATION THAT ASKED (`_emit_pool`'s own split,
    # unrelated to this lane) - the ROOT holds no project need at all here, so a
    # project-only run must land the whole 20 at the CHILD alone and write no row for the
    # root, exactly as a project buy is meant to land where the order was placed, not
    # wherever a leftover retail deficit happens to point the allocator.
    assert len(recs) == 1, f"expected exactly one line (at the child alone), got {recs}"
    assert buys, f"expected the one line to be a buy, got {recs}"
    assert float(buys[0]["rounded_qty"]) == 20.0, (
        f"expected the project need alone (20), got {buys[0]['rounded_qty']}"
    )
    assert (buys[0]["reason_label"] or "").startswith("project buy"), buys[0]["reason_label"]


def test_ac_po_4_dealer_run_with_same_seed_sizes_the_retail_top_up_not_20(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="retail", so_numbers=[],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "a Dealer run must still buy for the below-level product"
    # `demand_class='retail'` keeps ONLY the book leg of `horizon_committed_select_sql`
    # (`demand.py`'s own docstring) - a project-class SO's ORDER row is invisible to a
    # Dealer run's committed figure, so this is the SAME retail figure AC-PO-2 pins,
    # despite the qty-20 ORDER row seeded above it.
    expected = _expected_pool_retail_buy(demand_add=5.0, lead=30)
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == expected, (
        f"a Dealer run's figure is today's retail top-up ({expected}), not the project qty; got {total}"
    )
    assert total != 20.0


# ===========================================================================
# AC-PO-5 - so_numbers scope: a project row on an order OUTSIDE the picked list
# ===========================================================================

def test_ac_po_5_project_run_scoped_to_other_orders_emits_nothing_for_this_product(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    other_so_number = _code("OTHER-SO")

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[other_so_number],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], (
        f"a Project run scoped away from {so['so_number']} must not see its product, got {recs}"
    )


# ===========================================================================
# AC-PO-6 - a fully-linked ORDER row (owed 0) is not committed demand
# ===========================================================================

def test_ac_po_6_project_run_emits_nothing_for_a_fully_linked_order_row(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    row = so["rows"][0]
    supplier = Supplier(id=_u(), company_id=SORENTO_COMPANY_ID, supplier_code=_code("SUP"),
                        supplier_name=f"{MARKER} link supplier")
    po = PurchaseOrder(id=_u(), company_id=SORENTO_COMPANY_ID, po_number=_code("PO"),
                       supplier_id=supplier.id, status="active")
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(id=_u(), company_id=SORENTO_COMPANY_ID, purchase_order_id=po.id,
                                product_id=u["pid"], warehouse_id=u["child_wid"],
                                qty_ordered=row.qty, qty_received=0, line_status="open")
    db.add(po_line)
    db.flush()
    db.add(OrderInquiryLink(id=_u(), row_id=row.id, po_line_id=po_line.id, qty=row.qty,
                            document=po.po_number))
    db.flush()

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"a fully-linked row owes nothing; expected no line, got {recs}"


# ===========================================================================
# AC-PO-7 - MOQ / order multiple still round the project-alone need
# ===========================================================================

def test_ac_po_7_moq_rounds_the_project_need_alone(scm_app):
    _, db, _, _ = scm_app
    u = _seed_pool_below_level(db, moq=50, mult=50)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["child_wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "expected a buy for the project need"
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 50.0, (
        f"MOQ 50 must round the project need (20) up to 50 in total, got {total} "
        f"across {buys}"
    )


# ===========================================================================
# AC-PO-8 - a pooled product's sibling on-hand does not net a firm project Buy
# ===========================================================================

def test_ac_po_8_pooled_sibling_on_hand_does_not_reduce_the_project_buy(scm_app):
    _, db, _, _ = scm_app
    root_wid = _mk_warehouse(db, _code("ROOT"))
    child_wid = _mk_warehouse(db, _code("CHILD"), pool_warehouse_id=root_wid)
    pid = _mk_product(db, _code("P"))
    # Need at the CHILD (0 on hand), 100 sitting at the ROOT the pool could otherwise net
    # a firm project Buy against.
    _mk_stock(db, pid, child_wid, 0)
    _mk_stock(db, pid, root_wid, 100)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"), moq=1, mult=1)
    eng.ensure_reorder_policy_defaults(db)
    db.execute(text("UPDATE scm.reorder_policy SET pool_netting = true WHERE scope_type = 'global'"))
    db.flush()

    so = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": child_wid, "qty": 10,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    buys = _buy_rows(db, created["run_id"], pid)
    assert buys, "expected a buy for the firm project need"
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 10.0, (
        f"the sibling's 100 on hand must not net the firm project Buy, got {total} across {buys}"
    )


# ===========================================================================
# AC-PO-9 - the run header counts equal the sum of the emitted lines
# ===========================================================================

def test_ac_po_9_header_counts_equal_the_sum_of_the_lines_emitted(scm_app):
    """Two products in the SAME run: A has an acknowledged ORDER row (qty 20, no MOQ
    rounding) - the one line the run is entitled to; B is below its reorder level with NO
    project demand anywhere - AC-PO-1's own product, the leg-2 phantom this run must admit
    NOTHING for. The header counts must equal A's one line alone - B contributing a
    needs_level/buy/covered row of its own would be exactly the "phantom count from the
    dropped leg" AC-PO-9 exists to catch.
    """
    _, db, _, _ = scm_app
    a = _seed_single_below_level(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": a["pid"], "warehouse_id": a["wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    b = _seed_pool_below_level(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _recs_for(db, created["run_id"], b["pid"]) == [], (
        "product B (below level, no project demand) must contribute nothing"
    )

    run = db.execute(
        text("SELECT run_log FROM scm.reorder_run WHERE id = :id"), {"id": created["run_id"]},
    ).mappings().first()
    recs = db.execute(
        text("SELECT rec_type, rounded_qty, product_id::text AS product_id "
             "FROM scm.reorder_recommendation WHERE run_id = :id"),
        {"id": created["run_id"]},
    ).mappings().all()
    buy_count = sum(1 for r in recs if r["rec_type"] == "buy")
    assert run["run_log"]["buy"] == buy_count
    assert run["run_log"]["recommendation_count"] == len(recs)
    # A's own seed drives this: exactly one buy line, product A alone, sized 20 - no
    # phantom leg-2 recommendation riding along beside it.
    assert buy_count == 1, f"expected exactly one buy line, run_log={run['run_log']!r}"
    assert recs[0]["product_id"] == a["pid"]
    assert float(recs[0]["rounded_qty"]) == 20.0


# ===========================================================================
# PROD SHAPE (review round 2, item 1, blocker) - the 21 Sep prod copy carries ONE global
# policy row, `policy_type='reorder_level'`, `pool_netting=false`: every product sizes
# through `_emit_product`, never `_emit_pool`/plain `_emit_cell`. AC-PO-1/AC-PO-3's own
# twins, on that basis.
# ===========================================================================

def test_ac_po_3_reorder_level_basis_project_run_buys_exactly_the_order_qty(scm_app):
    """AC-PO-3's twin on the PROD basis. Kill: reverting `_emit_product`'s
    `if project_only:` branch (`reorder_run_service.py` ~:2301) to `if False:` falls
    through to the plain `reorder_level` trigger, which nets `agg_net` (on hand 0 minus
    the ORDER row's committed 20 = -20) against the level (150) and buys the WHOLE gap -
    170, not the order qty alone.
    """
    _, db, _, _ = scm_app
    u = _seed_single_below_level(db, demand_add=0.0)
    _use_reorder_level_policy(db)
    so = _project_so_with_lines(db, lines=[
        {"product_id": u["pid"], "warehouse_id": u["wid"], "qty": 20,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class="project", so_numbers=[so["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    buys = [r for r in recs if r["rec_type"] == "buy"]
    assert len(recs) == 1, f"expected exactly one line, got {recs}"
    assert buys, f"expected the one line to be a buy, got {recs}"
    assert float(buys[0]["rounded_qty"]) == 20.0, (
        f"expected the project need alone (20), NOT the level top-up (170), "
        f"got {buys[0]['rounded_qty']}"
    )
    assert (buys[0]["reason_label"] or "").startswith("project buy"), buys[0]["reason_label"]


def test_ac_po_1_reorder_level_basis_no_project_row_emits_nothing(scm_app):
    """AC-PO-1's twin on the PROD basis: below level, on hand 0, no project row anywhere -
    a Project run must admit nothing at all (S1, `_planning_rows`), so `_emit_product`
    never even runs for this product."""
    _, db, _, _ = scm_app
    u = _seed_single_below_level(db, demand_add=0.0)
    _use_reorder_level_policy(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="project", so_numbers=[])
    svc.run_reorder(created["run_id"], db=db)

    recs = _recs_for(db, created["run_id"], u["pid"])
    assert recs == [], f"expected no recommendation at all, got {recs}"


# ===========================================================================
# G10 (review round 2, item 5) - a NAMED product is buyer intent and keeps its retail
# sizing even under a Project run, `committed_gate_exempt`.
# ===========================================================================

def test_named_product_under_project_keeps_buyer_intent(scm_app):
    """A buyer who typed this SKU into Start Plan wants the SAME evaluation it would get
    outside a Project run (G10, `_planning_rows`' own doctrine: "a buyer who typed a SKU
    into Start Plan wants the SAME evaluation this product got before G1 existed") - so a
    Project run scoped to `product_ids=[pid]`, with NO project demand anywhere, must still
    buy the retail top-up to the level (150), not nothing. Today (before this lane) a
    named product under a Project run answers NOTHING: the project-only branches force
    `triggered = project_need > 0` unconditionally, discarding the retail sizing G10
    promises regardless of `product_ids`.
    """
    _, db, _, _ = scm_app
    u = _seed_single_below_level(db, demand_add=0.0)
    _use_reorder_level_policy(db)

    created = svc.create_run(db, [], enqueue=False, demand_class="project", so_numbers=[])
    # A narrowed run stores its scope as `run.product_ids` (`create_run`'s own
    # `product_codes` resolves to it); set it directly on the row rather than through a
    # product CODE, so this test pins the SAME `product_ids is not None` scope
    # `_planning_rows` reads, independent of the code-to-id resolution path.
    run = db.get(ReorderRun, created["run_id"])
    run.product_ids = [u["pid"]]
    db.add(run)
    db.flush()

    result = svc.run_reorder(created["run_id"], db=db)
    assert result["status"] == "completed", result

    buys = _buy_rows(db, created["run_id"], u["pid"])
    assert buys, "a named product must keep its retail sizing under a Project run (G10)"
    total = sum(float(b["rounded_qty"]) for b in buys)
    assert total == 150.0, (
        f"expected the level top-up (150) a named product gets outside a Project run, "
        f"got {total}"
    )
