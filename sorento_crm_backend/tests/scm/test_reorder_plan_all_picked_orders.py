"""RED tests, written before the coder's Phase 2, for Lane D of
`PLAN-order-sheet-oi-reports-22sep.md` (AC-D1..D6 in
`order-sheet-oi-reports-22sep-acceptance-criteria.md`).

Lane D: Start Plan with Demand = All accepts a picked `so_numbers` list alongside NO
`demand_class` - the Orders picker narrows only the two PROJECT legs (confirmed + form)
of an All run's committed figure; the retail SO-book leg and leg-2 admission stay
untouched, so the retail side still sizes from the level trigger. Backend-only (D1's FE
picker/trigger-label change is vitest, in
`sorento_crm_frontend/app/(protected)/scm/reorder/components/RunPlanningModal.test.tsx`).

STEP 1 MEASURE (captain's brief, 23 Sep 2026), confirmed on this branch before writing
these tests:

  (a) `CreateReorderRunRequest`/`ReplanReorderRunRequest`
      (`app/schemas/scm_reorder.py::require_so_numbers_need_project_demand_class`) RAISES
      when `so_numbers` is non-empty and `demand_class != "project"` - so an All run
      (`demand_class` absent) carrying `so_numbers` is refused 422 at the HTTP layer
      TODAY. `tests/test_reorder_plan_demand_scope.py::test_t2_so_numbers_without_
      project_demand_class_is_refused` already pins BOTH the omitted-demand_class case
      AND the retail case as 422 - Lane D changes the CONTRACT for the omitted case only
      (AC-D2), so that existing test's "omitted" assertion will need to flip to 202 as
      part of this lane's implementation; its "retail" assertion (AC-D6) stays 422 and
      must not move. Flagged here rather than silently edited, since editing another
      lane's already-landed pinned test is the coder's job, not the tester's.

  (b) `reorder_run_service._planning_rows` line ~917: `so_scoped = bool(so_numbers)` is
      ALREADY independent of `demand_class` - `demand.horizon_committed_select_sql`
      already narrows the two project legs whenever `so_numbers` is non-empty, whatever
      `demand_class` is (an existing test proves this for `demand_class="retail"`,
      `test_t6_retail_counts_the_retail_line_plus_unlocated_and_ignores_so_numbers` -
      it deliberately calls `so_numbers=[so_a]` with `demand_class="retail"` and gets the
      SO-scoped confirmed+form figure). So a DIRECT `create_run`/`_planning_rows` call
      (bypassing the HTTP schema, as `test_t6` already does) with `demand_class=None` and
      `so_numbers=[...]` should ALREADY narrow `committed` correctly - confirmed by
      `test_ac_d2_service_level_committed_already_scoped_on_all_run_bypassing_http` below
      running GREEN before any coder change (a regression guard for AC-D2/AC-D3's
      `committed` half, not a red test - the red half is the HTTP schema, (a) above).

  (c) `_apply_project_supply_reduction` (`reorder_run_service.py` ~1320-1336) gates its
      OWN so-scoping on `demand_class == "project"` specifically:
      `scoped_so_numbers = so_numbers if (so_numbers and demand_class == "project") else
      None`. On an All run (`demand_class=None`) this reads as unscoped - EVERY confirmed
      Project reserve claim reduces available stock, not only the picked SO's - which is
      the plan's own D2 callout ("`_apply_project_supply_reduction` ... read `so_numbers`
      whenever set, not only under Project"). `test_t6` above pins that dropping the
      `demand_class` check ENTIRELY would be wrong for a retail run (claimed stock is
      real supply regardless of which leg a retail run examines), so the fix this lane
      needs is narrower than "drop the check" - it excludes `demand_class == "retail"`
      specifically, not `so_numbers` truthiness alone. `test_ac_d2_project_supply_
      reduction_scoped_by_so_numbers_on_all_run` below is genuinely RED today (asserts 6.0,
      the SO-A-only claim; today's code answers 8.0, both SOs' claims, since `None !=
      "project"` takes the same branch as never-scoped).

  (d) `demand.horizon_committed_select_sql`'s retail (SO-book) leg (`demand.py` ~702-726)
      is windowed by `:horizon`/`:horizon_start` on EVERY run today, with no
      `retail_windowed` parameter - AC-D1b (an All run's range narrows the PROJECT legs
      only; the retail leg plans every open line regardless of the range) is not built.
      `test_ac_d1b_all_run_range_narrows_project_leg_only_retail_leg_unbounded` below is
      genuinely RED: the retail line due AFTER `plan_horizon_date` is excluded from
      `committed` today on an All run exactly as on a Dealer run, and this test asserts it
      must stay IN on an All run.

Harness copied from `tests/scm/test_m3_run.py` (`_client`, `_mk_*`),
`tests/test_reorder_plan_demand_scope.py` (`_seed_scope_universe`, `_inputs_for`,
`_client`, `_project_so_with_lines`, `_add_reserve_claim`) and
`tests/scm/test_reorder_plan_project_only.py` (`_seed_pool_below_level`,
`_expected_pool_retail_buy`, `_recs_for`/`_buy_rows`). Postgres only, via
`tests/scm/conftest.py::scm_app` - a live TestClient over a rolled-back SAVEPOINT. CI's
database starts empty: every test seeds its own full chain, nothing borrowed off the
shared local database.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.project_so import ACK_ACKNOWLEDGED
from app.models.scm import ReorderRun
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg, scm_app  # noqa: F401
from tests.scm.test_m3_run import (
    _client,
    _link,
    _mk_demand,
    _mk_movement,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)
from tests.scm.test_reorder_plan_project_only import (
    _expected_pool_retail_buy,
    _seed_pool_below_level,
)
from tests.test_reorder_plan_demand_scope import (
    _add_reserve_claim,
    _committed_for,
    _inputs_for,
    _project_so_with_lines,
    _retail_row,
    _seed_scope_universe,
)

pytestmark = requires_pg

MARKER = "ZZTPAO"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _buy_rows(db, run_id: str, pid: str) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT rec_type, rounded_qty FROM scm.reorder_recommendation "
            "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
        ),
        {"r": run_id, "p": pid},
    ).mappings().all()
    return [dict(r) for r in rows]


# =============================================================================
# AC-D2 - the route accepts so_numbers with no demand_class; the run row stores both.
# =============================================================================

def test_ac_d2_all_run_with_so_numbers_and_no_demand_class_is_accepted(scm_app):
    """RED today: `require_so_numbers_need_project_demand_class` raises 422 whenever
    `so_numbers` is non-empty and `demand_class != "project"`, so an omitted
    `demand_class` (All) is refused exactly like a stated `retail` one. Fixed shape:
    2xx, `demand_class` stays NULL, `so_numbers` stored as sent.
    """
    app, db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": [], "so_numbers": ["SO1", "SO2"],
        })
        assert resp.status_code == 202, resp.text
        run_id = resp.json()["run_id"]

        stored = db.execute(
            text("SELECT demand_class, so_numbers FROM scm.reorder_run WHERE id = :id"),
            {"id": run_id},
        ).mappings().first()
        assert stored is not None
        assert stored["demand_class"] is None
        assert list(stored["so_numbers"] or []) == ["SO1", "SO2"]

        status = c.get(f"/api/v1/scm/reorder-runs/{run_id}")
        assert status.status_code == 200, status.text
        body = status.json()
        assert body["demand_class"] is None
        assert body["so_numbers"] == ["SO1", "SO2"]


# =============================================================================
# AC-D2/AC-D3 - service level: committed already scoped (regression guard), supply
# reduction not yet scoped (genuinely red).
# =============================================================================

def test_ac_d2_service_level_committed_already_scoped_on_all_run_bypassing_http(scm_app):
    """GREEN today (regression guard, not a red test - see module docstring (b)): calling
    `create_run` directly with `demand_class=None`, `so_numbers=[so_a]` (bypassing the
    HTTP schema the same way `test_t6` already does for `demand_class='retail'`) already
    narrows `committed` to SO A's own rows: retail (7) + unlocated (9) + SO A's confirmed
    (11) + SO A's form row (5) = 32 - SO B's confirmed (13) and form (3) rows must not
    leak in.
    """
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class=None, so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    assert _committed_for(db, created["run_id"], u["pid"]) == 32.0


def test_ac_d2_project_supply_reduction_scoped_by_so_numbers_on_all_run(scm_app):
    """RED today: `_apply_project_supply_reduction`'s `scoped_so_numbers = so_numbers if
    (so_numbers and demand_class == "project") else None` reads `demand_class=None` (All)
    the same as never-scoped, so it answers BOTH SOs' reserve claims (6 + 2 = 8). Fixed
    shape (plan D2: "`_apply_project_supply_reduction` ... read `so_numbers` whenever
    set, not only under Project"): SO A's own claim alone (6) - SO B's (2) must not leak
    in, on an All run just as on a Project run (`test_t4`'s own pin).
    """
    _, db, _, _ = scm_app
    u = _seed_scope_universe(db)

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class=None, so_numbers=[u["so_a"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    inputs = _inputs_for(db, created["run_id"], u["pid"])["inputs"]
    assert float(inputs.get("committed") or 0) == 32.0
    assert float(inputs.get("project_supply_reduction") or 0) == 6.0


# =============================================================================
# AC-D3/AC-D4 - sizing: a picked SO's project need is bought in full on top of retail
# sizing; a product whose only project demand sits on an un-picked SO gets none; a
# retail-only product is unaffected.
# =============================================================================

def test_ac_d3_picked_so_project_need_bought_in_full_on_top_of_retail_sizing(scm_app):
    """GREEN today for the COMMITTED half (b) - RED for the recommended QTY, because it
    depends on AC-D2's supply-reduction fix having no seeded reserve claim here (so this
    test alone would not catch that gap; `test_ac_d2_project_supply_reduction_scoped_
    by_so_numbers_on_all_run` does). Two pooled products, each below its own level (leg 2
    admits both regardless of committed demand): P1 carries a project OI row on the
    PICKED SO (so_a, qty 40, in window); P2 carries one on an UN-PICKED SO (so_b, qty 25,
    in window). An All run scoped to `so_numbers=[so_a]`:

    - P1's Buy = its own pool retail figure + 40 (project need in full, R1a - no netting).
    - P2's Buy = its own pool retail figure ALONE - so_b's 25 must not reach `committed`
      at all, so P2's `project_need` display is 0 (D3's own wording: "a product whose only
      project demand sits on an un-picked SO carries no project need").
    """
    _, db, _, _ = scm_app
    u1 = _seed_pool_below_level(db, level=150, demand_add=5.0, lead=30)
    u2 = _seed_pool_below_level(db, level=200, demand_add=8.0, lead=20)

    so_a = _project_so_with_lines(db, lines=[
        {"product_id": u1["pid"], "warehouse_id": u1["root_wid"], "qty": 40,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])
    so_b = _project_so_with_lines(db, lines=[
        {"product_id": u2["pid"], "warehouse_id": u2["root_wid"], "qty": 25,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    created = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class=None, so_numbers=[so_a["so_number"]],
    )
    svc.run_reorder(created["run_id"], db=db)

    p1_buys = _buy_rows(db, created["run_id"], u1["pid"])
    p1_total = sum(float(r["rounded_qty"]) for r in p1_buys)
    p1_retail_only = _expected_pool_retail_buy(demand_add=5.0, lead=30)
    assert p1_total == p1_retail_only + 40.0, (
        f"expected retail ({p1_retail_only}) + picked-SO project need in full (40), "
        f"got {p1_total}"
    )

    p2_buys = _buy_rows(db, created["run_id"], u2["pid"])
    p2_total = sum(float(r["rounded_qty"]) for r in p2_buys)
    p2_retail_only = _expected_pool_retail_buy(demand_add=8.0, lead=20)
    assert p2_total == p2_retail_only, (
        f"un-picked SO's 25 must not reach this product's Buy at all, "
        f"expected retail-only ({p2_retail_only}), got {p2_total}"
    )

    inputs2 = _inputs_for(db, created["run_id"], u2["pid"])["inputs"]
    assert float(inputs2.get("committed") or 0) == 0.0, (
        "P2's only project demand sits on the un-picked SO - committed must be 0"
    )


def test_ac_d4_retail_only_product_still_admitted_and_sized_same_as_plain_all_run(scm_app):
    """A retail-only product (no project demand anywhere) below its level, on an All run
    with `so_numbers=[so_a]` set for an UNRELATED product - leg 2 still admits it and
    sizes it from the level trigger exactly as an All run with no `so_numbers` at all.
    Regression guard: this is the part of D2/D4 the plan says stays UNTOUCHED
    ("the retail SO-book leg and leg-2 admission are untouched").
    """
    _, db, _, _ = scm_app
    retail_u = _seed_pool_below_level(db, level=120, demand_add=4.0, lead=15)
    other_u = _seed_pool_below_level(db, level=150, demand_add=5.0, lead=30)
    so_a = _project_so_with_lines(db, lines=[
        {"product_id": other_u["pid"], "warehouse_id": other_u["root_wid"], "qty": 40,
         "delivery_date": date(2026, 10, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    scoped = svc.create_run(
        db, [], enqueue=False,
        plan_horizon_start=date(2026, 1, 1), plan_horizon_date=date(2026, 12, 31),
        demand_class=None, so_numbers=[so_a["so_number"]],
    )
    svc.run_reorder(scoped["run_id"], db=db)

    buys = _buy_rows(db, scoped["run_id"], retail_u["pid"])
    total = sum(float(r["rounded_qty"]) for r in buys)
    expected = _expected_pool_retail_buy(demand_add=4.0, lead=15)
    assert total == expected, (
        f"retail-only product's Buy must be unaffected by an unrelated so_numbers scope, "
        f"expected {expected}, got {total}"
    )


# =============================================================================
# AC-D1b - on an All run the range narrows the PROJECT legs only; the retail (SO-book)
# leg plans every open line regardless of the range.
# =============================================================================

def test_ac_d1b_all_run_range_narrows_project_leg_only_retail_leg_unbounded(scm_app):
    """RED today: `demand.horizon_committed_select_sql`'s retail leg has no
    `retail_windowed` switch - `:horizon`/`:horizon_start` bind it on every run, All
    included, so a retail line due AFTER `plan_horizon_date` is excluded from `committed`
    on an All run exactly as on a Dealer run. AC-D1b: on an All run it must stay IN; the
    project leg (a confirmed row due after the date) must still be excluded, same as
    today.

    Both runs are scoped to `product_codes=[code]` (fix round 1: G10's named-product
    admission bypass - `_planning_rows`' own docstring, "a run given explicit
    product_ids plans those products regardless of committed demand") - product_ids
    exempts the row from G1's ADMISSION gate, but G10 does not manufacture a
    recommendation out of nothing: `_emit_cell`/`_covered_rec` still write no row at
    all for a cell with zero committed AND nothing else to report (`_covered_rec`:
    "None when the pool has no committed demand at all - that is genuinely nothing to
    say"). So this product ALSO gets an explicit product-wide `scm.reorder_level` row
    and a nonzero forecast (`_seed_pool_below_level`'s own pattern) - stock (0) below
    that level triggers a REAL `buy` row on every run regardless of `committed`, which
    is what makes the Dealer run's `committed = 0` actually OBSERVABLE via
    `_committed_for` rather than erroring "no recommendation row".
    """
    _, db, _, _ = scm_app
    code = _code("P")
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, code)
    _mk_stock(db, pid, wid, 0)
    _mk_demand(db, pid, wid, 5.0)
    _mk_movement(db, pid, wid, 1, days_ago=7)
    _link(db, pid, _mk_supplier(db, f"{MARKER} Supplier"))
    eng.ensure_reorder_policy_defaults(db)
    db.execute(
        text(
            "INSERT INTO scm.reorder_level (id, product_id, warehouse_id, level, source, "
            "company_id, created_at) VALUES (:id, :p, NULL, :lvl, 'manual', :co, now())"
        ),
        {"id": _u(), "p": pid, "lvl": 10, "co": SORENTO_COMPANY_ID},
    )
    db.flush()

    # Retail line due AFTER the plan's range end.
    _retail_row(db, product_id=pid, warehouse_id=wid, qty=12, so_number=_code("SOR"),
                required_date=date(2026, 12, 1))
    # Project row also due after the range end - must stay excluded either way.
    so = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 20,
         "delivery_date": date(2026, 12, 1), "ack_state": ACK_ACKNOWLEDGED},
    ])

    all_run = svc.create_run(
        db, [], enqueue=False, product_codes=[code],
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class=None, so_numbers=[so["so_number"]],
    )
    svc.run_reorder(all_run["run_id"], db=db)
    all_committed = _committed_for(db, all_run["run_id"], pid)

    dealer_run = svc.create_run(
        db, [], enqueue=False, product_codes=[code],
        plan_horizon_start=date(2026, 8, 1), plan_horizon_date=date(2026, 10, 31),
        demand_class="retail", so_numbers=[],
    )
    svc.run_reorder(dealer_run["run_id"], db=db)
    dealer_committed = _committed_for(db, dealer_run["run_id"], pid)

    assert all_committed == 12.0, (
        f"All run: the retail line due after the range end must still count (12), "
        f"the project row must stay excluded (0) - got {all_committed}"
    )
    assert dealer_committed == 0.0, (
        f"Dealer run: unchanged, the same retail line due after the range end is "
        f"excluded - got {dealer_committed}"
    )


# =============================================================================
# AC-D6 - Demand = Dealer (retail) with so_numbers is unaffected by this lane; Project
# behaves as PR #1122 left it (not re-pinned here - see test_reorder_plan_project_only.py).
# =============================================================================

def test_ac_d6_dealer_run_with_so_numbers_stays_refused_at_the_http_layer(scm_app):
    """Pin: AC-D2 widens the schema's acceptance to the omitted-demand_class case ONLY -
    a stated `demand_class='retail'` with `so_numbers` set must still be refused 422,
    unchanged (`test_t2`'s own "retail" half already pins this; restated here as this
    lane's own regression guard so it is not lost if that file's other half is edited for
    AC-D2)."""
    app, _db = _client(scm_app, "purchasing")

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/reorder-runs", json={
            "warehouse_codes": [], "demand_class": "retail", "so_numbers": ["SO1"],
        })
    assert resp.status_code == 422, resp.text
