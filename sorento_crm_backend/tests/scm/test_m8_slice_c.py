"""SCM M8 Slice C - pin/reject-aware budget split + full-budget funding (backend parity).

Two halves, mirroring ``test_m4_cash``:

  * PURE maths (no DB) - ``cash_ranking.allocate_funding`` gains ``pinned_ids`` /
    ``rejected_ids`` / full-budget (``budget=None`` or ``full=True``). Golden numbers
    are hand-authored here, derived INDEPENDENTLY of the allocator, to lock the
    "pins win + consume budget first, rejects excluded, uncosted still needs_cost,
    un-pinned greedy fills the leftover" semantics the FE ``computeFundingM8``
    already implements client-side (M8-C2/C3/C7).
  * DB-backed - ``apply_run_budget`` derives pins (accepted/adjusted) + rejects
    (dismissed) from the decision overlay so the PERSISTED ``funding_status`` matches
    the live FE split, plus the full-budget persist path (daily-cron style).

DB tests reuse the ``scm_app`` savepoint fixture + ``purchasing`` role, and the
fixture builders from ``test_m4_cash`` (as ``test_m4_decisions`` does).
"""
from __future__ import annotations

from sqlalchemy import text

from app.services.scm import cash_ranking as cr
from app.services.scm import decision_service as dsvc
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg, set_plan_grain
from tests.scm.test_m4_cash import _client, _seed_two_buys

pytestmark = requires_pg


def _buys(*specs) -> list[cr.Buy]:
    """specs = (id, rank, cash_impact)."""
    return [cr.Buy(id=i, rank=rk, cash_impact=c) for (i, rk, c) in specs]


# ===========================================================================
# PURE - pins win + consume budget first (M8-C3)
# ===========================================================================

def test_pin_forces_fund_and_consumes_budget_first():
    """A pinned rank-3 buy funds FIRST and eats the budget, so higher-ranked un-pinned
    buys that would otherwise fund now defer. budget 8000; pin c (4000) → funded,
    remaining 4000; a (6000) overflow → deferred; b (5000) overflow → deferred."""
    result = cr.allocate_funding(
        _buys(("a", 1, 6000), ("b", 2, 5000), ("c", 3, 4000)),
        budget=8000, pinned_ids={"c"})
    assert result.status_by_id == {"a": "deferred", "b": "deferred", "c": "funded"}
    assert result.funded_count == 1 and result.deferred_count == 2
    assert result.funded_cash == 4000 and result.deferred_cash == 11000


def test_pin_over_budget_stays_funded_free_goes_negative():
    """Two pinned buys totalling 8000 against a 6000 budget BOTH stay funded - a pin
    never drops to deferred on an overspend; funded_cash (8000) exceeds budget and the
    free figure (budget − funded) goes negative (−2000), matching the FE."""
    budget = 6000
    result = cr.allocate_funding(
        _buys(("a", 1, 5000), ("b", 2, 3000)),
        budget=budget, pinned_ids={"a", "b"})
    assert result.status_by_id == {"a": "funded", "b": "funded"}
    assert result.funded_count == 2 and result.deferred_count == 0
    assert result.funded_cash == 8000            # > budget, pins don't drop
    assert budget - result.funded_cash == -2000  # free is negative on overspend


def test_pinned_buy_funds_even_with_zero_budget():
    """A pinned costed buy funds even at budget 0 (consumes budget first, free negative);
    the un-pinned costed buy defers."""
    result = cr.allocate_funding(
        _buys(("a", 1, 5000), ("b", 2, 3000)),
        budget=0, pinned_ids={"a"})
    assert result.status_by_id == {"a": "funded", "b": "deferred"}
    assert result.funded_cash == 5000 and result.deferred_cash == 3000


# ===========================================================================
# PURE - rejects excluded entirely (M8-C3)
# ===========================================================================

def test_rejected_buy_excluded_from_every_bucket():
    """A rejected buy appears in NO bucket (not funded/deferred/needs_cost) and never
    draws from the budget; the rest allocate as if it did not exist."""
    result = cr.allocate_funding(
        _buys(("a", 1, 5000), ("b", 2, 3000), ("c", 3, None)),
        budget=10000, rejected_ids={"a"})
    assert result.status_by_id == {"b": "funded", "c": "needs_cost"}
    assert "a" not in result.status_by_id
    assert result.funded_count == 1 and result.deferred_count == 0
    assert result.needs_cost_count == 1 and result.funded_cash == 3000


# ===========================================================================
# PURE - un-pinned greedy fills the leftover by rank (M8-C2)
# ===========================================================================

def test_unpinned_greedy_fills_leftover_by_rank():
    """After a pinned buy eats part of the budget, the un-pinned buys fill the remainder
    greedily by rank (skip-overflow). budget 10000; pin d (5000) → remaining 5000;
    a (4000) fits → remaining 1000; b (3000) overflow → deferred; c (2000) overflow →
    deferred."""
    result = cr.allocate_funding(
        _buys(("a", 1, 4000), ("b", 2, 3000), ("c", 3, 2000), ("d", 4, 5000)),
        budget=10000, pinned_ids={"d"})
    assert result.status_by_id == {"a": "funded", "b": "deferred",
                                   "c": "deferred", "d": "funded"}
    assert result.funded_count == 2 and result.funded_cash == 9000
    assert result.deferred_cash == 5000


# ===========================================================================
# PURE - uncosted stays needs_cost even when pinned (M8-C7)
# ===========================================================================

def test_pinned_uncosted_buy_stays_needs_cost():
    """A pin cannot fund an unknown cost - a pinned UNCOSTED buy stays needs_cost and
    draws nothing from the budget; the un-pinned costed buy still funds/defers."""
    result = cr.allocate_funding(
        _buys(("a", 1, None), ("b", 2, 3000)),
        budget=10000, pinned_ids={"a"})
    assert result.status_by_id == {"a": "needs_cost", "b": "funded"}
    assert result.needs_cost_count == 1 and result.funded_cash == 3000


# ===========================================================================
# PURE - full budget funds all costed (M8 daily-cron path)
# ===========================================================================

def test_full_budget_none_funds_all_costed():
    """budget=None means FULL budget: every costed buy funds, uncosted still needs_cost,
    nothing defers. (This inverts the pre-M8 budget=None meaning of 'fund nothing'.)"""
    result = cr.allocate_funding(
        _buys(("a", 1, 5000), ("b", 2, 3000), ("c", 3, None)), budget=None)
    assert result.status_by_id == {"a": "funded", "b": "funded", "c": "needs_cost"}
    assert result.funded_count == 2 and result.deferred_count == 0
    assert result.needs_cost_count == 1 and result.funded_cash == 8000


def test_full_flag_funds_all_costed_ignoring_small_budget():
    """``full=True`` funds all costed regardless of the numeric budget (a tiny budget
    that would otherwise defer most buys)."""
    result = cr.allocate_funding(
        _buys(("a", 1, 5000), ("b", 2, 3000)), budget=1, full=True)
    assert result.status_by_id == {"a": "funded", "b": "funded"}
    assert result.deferred_count == 0 and result.funded_cash == 8000


def test_full_budget_still_excludes_rejects():
    """Full budget funds all costed EXCEPT rejected buys (excluded) and uncosted
    (needs_cost)."""
    result = cr.allocate_funding(
        _buys(("a", 1, 5000), ("b", 2, 3000), ("c", 3, None)),
        budget=None, rejected_ids={"a"})
    assert result.status_by_id == {"b": "funded", "c": "needs_cost"}
    assert "a" not in result.status_by_id and result.funded_cash == 3000


# ===========================================================================
# DB - apply_run_budget persists the pin/reject-aware split (M8-C3 parity)
# ===========================================================================

def test_apply_budget_pins_accepted_regardless_of_rank(scm_app):
    """A manually ACCEPTED buy is force-funded on persist even when the budget is 0 and
    its rank is lower - it consumes budget first; the un-pinned buy defers."""
    app, db = _client(scm_app, "purchasing")
    _, a, b = _seed_two_buys(db)
    # Accept / reject below are LOCATION-grain decisions (front planning 5.4), so the run
    # has to be created under the location policy or it owns the Product decision instead.
    set_plan_grain(db, "location")
    created = svc.create_run(db, ["M4W-CASH"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rid = created["run_id"]

    recs = db.execute(text(
        "SELECT id::text AS id, product_id::text AS pid, rank "
        "FROM scm.reorder_recommendation WHERE run_id = :r AND rec_type = 'buy'"
    ), {"r": rid}).mappings().all()
    by_pid = {r["pid"]: r for r in recs}
    # accept the CALM buy (higher rank number) - a pin must win over rank + zero budget
    dsvc.accept_recommendation(db, by_pid[b]["id"], None)
    db.flush()

    out = svc.apply_run_budget(db, rid, 0.0)
    status = dict(db.execute(text(
        "SELECT id::text, funding_status FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND rec_type = 'buy'"), {"r": rid}).all())
    assert status[by_pid[b]["id"]] == "funded"      # pinned → funded despite 0 budget
    assert status[by_pid[a]["id"]] == "deferred"    # un-pinned defers at 0 budget
    assert out["funded_count"] == 1 and out["deferred_count"] == 1


def test_apply_budget_excludes_dismissed(scm_app):
    """A manually REJECTED (dismissed) buy is excluded from the persisted split - its
    funding_status is cleared, and it is not counted as funded/deferred."""
    app, db = _client(scm_app, "purchasing")
    _, a, b = _seed_two_buys(db)
    # Accept / reject below are LOCATION-grain decisions (front planning 5.4), so the run
    # has to be created under the location policy or it owns the Product decision instead.
    set_plan_grain(db, "location")
    created = svc.create_run(db, ["M4W-CASH"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rid = created["run_id"]

    recs = db.execute(text(
        "SELECT id::text AS id, product_id::text AS pid FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND rec_type = 'buy'"), {"r": rid}).mappings().all()
    by_pid = {r["pid"]: r for r in recs}
    dsvc.reject_recommendation(db, by_pid[a]["id"], "not needed", None)
    db.flush()

    out = svc.apply_run_budget(db, rid, 10_000_000.0)
    status = dict(db.execute(text(
        "SELECT id::text, funding_status FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND rec_type = 'buy'"), {"r": rid}).all())
    assert status[by_pid[a]["id"]] is None          # dismissed → excluded, cleared
    assert status[by_pid[b]["id"]] == "funded"
    assert out["funded_count"] == 1 and out["deferred_count"] == 0


def test_apply_full_budget_persists_all_costed_funded(scm_app):
    """The full-budget persist path (budget=None / full) funds every costed buy and
    stamps a null budget_amount on the run."""
    app, db = _client(scm_app, "purchasing")
    _seed_two_buys(db)
    created = svc.create_run(db, ["M4W-CASH"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rid = created["run_id"]

    out = svc.apply_run_budget(db, rid, None, full=True)
    statuses = db.execute(text(
        "SELECT funding_status FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND rec_type = 'buy'"), {"r": rid}).scalars().all()
    assert statuses and all(s == "funded" for s in statuses)
    assert out["funded_count"] == 2 and out["deferred_count"] == 0
    assert out["budget"] is None
    run = db.execute(text(
        "SELECT budget_amount FROM scm.reorder_run WHERE id = :r"), {"r": rid}
    ).mappings().first()
    assert run["budget_amount"] is None


# ===========================================================================
# DB - PUT /budget full-budget request (null amount → fund all)
# ===========================================================================

def test_put_budget_full_request_funds_all(scm_app):
    """PUT /budget with ``full: true`` (no numeric budget) persists every costed buy as
    funded - the daily-cron / 'fund all within budget' path."""
    from fastapi.testclient import TestClient

    app, db = _client(scm_app, "purchasing")
    _seed_two_buys(db)
    created = svc.create_run(db, ["M4W-CASH"], "warehouse", enqueue=False)
    svc.run_reorder(created["run_id"], db=db)
    rid = created["run_id"]

    with TestClient(app) as c:
        put = c.put(f"/api/v1/scm/reorder-runs/{rid}/budget", json={"full": True})
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["funded_count"] == 2 and body["deferred_count"] == 0
        assert body["budget"] is None

        got = c.get(f"/api/v1/scm/reorder-runs/{rid}/recommendations",
                    params={"type": "buy", "limit": 500})
        assert all(r["funding_status"] == "funded"
                   for r in got.json()["data"] if r["type"] == "buy")
