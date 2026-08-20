"""S16 (captain 21 Aug, 3rd time requested) — the row decision: buy / use stock /
use PO / skip, or a mixture, recorded directly on a recommendation.

> "I want the decision made here... there is only buy / use stock / use SPO / mixture,
>  right" / "why is the decision still a hyperlink, instead of you give me a hyperlink"

Drives `decision_service.record_plan_row_decision` / `clear_plan_row_decision` /
`list_plan_row_decisions` directly, plus the two routes and `confirm_decisions`'
new plan_row_decision-aware reconciliation, against controlled fixtures inside the
`scm_app` savepoint (mirrors `test_m4_decisions.py`).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.error_handler import AppException
from app.services.scm import decision_service as dsvc
from app.services.scm import reorder_run_service as run_svc
from tests.scm.conftest import requires_pg, set_plan_grain
from tests.scm.test_covered_decision import _covered_row
from tests.scm.test_m4_cash import (
    _client,
    _link,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


# ===========================================================================
# fixtures
# ===========================================================================

def _run_buys(db, wid_code) -> str:
    set_plan_grain(db, "location")
    created = run_svc.create_run(db, [wid_code], "warehouse", enqueue=False)
    assert run_svc.run_reorder(created["run_id"], db=db)["status"] == "completed"
    return created["run_id"]


def _buy_rec(db, wid_code, product_code):
    wid = _mk_warehouse(db, wid_code)
    pid = _mk_product(db, product_code)
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 10.0)
    _link(db, pid, _mk_supplier(db, f"S16 Supplier {product_code}"), cost=60)
    db.flush()
    run_id = _run_buys(db, wid_code)
    rec = db.execute(text(
        "SELECT id::text AS id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": run_id, "p": pid}).mappings().first()
    assert rec is not None, "fixture must produce a buy row"
    return run_id, rec["id"], wid_code


def _decision_row(db, rec_id):
    return db.execute(text(
        "SELECT kind, buy_qty, stock_takes, po_qty, po_refs, reason_text "
        "FROM scm.plan_row_decision WHERE recommendation_id = :r"
    ), {"r": rec_id}).mappings().first()


# ===========================================================================
# record — every kind, incl. a mixture summing correctly
# ===========================================================================

def test_record_buy_decision(scm_app):
    _, db, _, _ = scm_app
    run_id, rec_id, _wid = _buy_rec(db, "S16W-BUY", "S16P-BUY")

    out = dsvc.record_plan_row_decision(
        db, rec_id, "buy", 150, [], None, [], "reorder point breached", "tester"
    )
    assert out["kind"] == "buy"
    assert out["buy_qty"] == 150
    assert out["draft_po_number"] is None  # staged, not materialised

    row = _decision_row(db, rec_id)
    assert row["kind"] == "buy"
    assert float(row["buy_qty"]) == 150
    assert row["reason_text"] == "reorder point breached"


def test_record_skip_decision(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-SKIP", "S16P-SKIP")

    out = dsvc.record_plan_row_decision(
        db, rec_id, "skip", None, [], None, [], "not this cycle", "tester"
    )
    assert out["kind"] == "skip"
    assert out["buy_qty"] is None

    row = _decision_row(db, rec_id)
    assert row["kind"] == "skip"
    assert row["buy_qty"] is None


def test_record_use_po_decision(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-USEPO", "S16P-USEPO")

    out = dsvc.record_plan_row_decision(
        db, rec_id, "use_po", None, [], 40, ["PO-2026/08-0099"], "already on order", "tester"
    )
    assert out["kind"] == "use_po"
    assert out["po_qty"] == 40
    assert out["po_refs"] == ["PO-2026/08-0099"]


def test_record_mixture_sums_correctly(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid_code = _buy_rec(db, "S16W-MIX", "S16P-MIX")
    other_wh_code = "S16W-MIX-BIN"
    _mk_warehouse(db, other_wh_code)
    db.flush()

    out = dsvc.record_plan_row_decision(
        db, rec_id, "mixture",
        50,
        [{"location": other_wh_code, "qty": 30}],
        20,
        ["PO-2026/08-0100"],
        "partial buy, partial stock, partial already on PO",
        "tester",
    )
    assert out["kind"] == "mixture"
    assert out["buy_qty"] == 50
    assert out["po_qty"] == 20
    assert len(out["stock_takes"]) == 1
    assert out["stock_takes"][0]["location"] == other_wh_code
    assert out["stock_takes"][0]["qty"] == 30

    row = _decision_row(db, rec_id)
    assert row["kind"] == "mixture"
    assert float(row["buy_qty"]) == 50
    assert float(row["po_qty"]) == 20
    takes = row["stock_takes"]
    assert len(takes) == 1
    assert takes[0]["qty"] == 30
    # the three parts sum to the mixture the buyer actually recorded
    total = float(row["buy_qty"]) + sum(t["qty"] for t in takes) + float(row["po_qty"])
    assert total == 100


# ===========================================================================
# clear
# ===========================================================================

def test_clear_decision_is_idempotent(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-CLEAR", "S16P-CLEAR")
    dsvc.record_plan_row_decision(db, rec_id, "buy", 10, [], None, [], None, "tester")
    assert _decision_row(db, rec_id) is not None

    out = dsvc.clear_plan_row_decision(db, rec_id, "tester")
    assert out["cleared"] is True
    assert _decision_row(db, rec_id) is None

    # clearing again is a no-op, not an error
    out2 = dsvc.clear_plan_row_decision(db, rec_id, "tester")
    assert out2["cleared"] is False


# ===========================================================================
# a non-buy rec accepts use_stock (S16 gap #2 — the buy-only guard is relaxed)
# ===========================================================================

def test_non_buy_rec_accepts_use_stock(scm_app):
    _, db, _, _ = scm_app
    db, rec_id = _covered_row(db)

    out = dsvc.record_plan_row_decision(
        db, rec_id, "use_stock", None,
        [{"location": "ZZTW-DEC", "qty": 5}], None, [], "keep the stock", "tester",
    )
    assert out["kind"] == "use_stock"
    assert out["stock_takes"][0]["qty"] == 5

    row = _decision_row(db, rec_id)
    assert row["kind"] == "use_stock"

    # the OLD buy-only accept/adjust/reject path still refuses this same row —
    # the relaxation is additive, not a removal of the old invariant.
    with pytest.raises(AppException):
        dsvc.accept_recommendation(db, rec_id, actor="tester")


def test_exception_rec_type_is_refused(scm_app):
    """The one invariant kept: a rec_type the grid never shows can't carry a decision."""
    _, db, _, _ = scm_app
    _run_id, buy_rec_id, _wid = _buy_rec(db, "S16W-EXC", "S16P-EXC")
    exc_id = str(uuid.uuid4())
    run_id = db.execute(text(
        "SELECT run_id::text FROM scm.reorder_recommendation WHERE id = :r"
    ), {"r": buy_rec_id}).scalar()
    pid = db.execute(text(
        "SELECT product_id::text FROM scm.reorder_recommendation WHERE id = :r"
    ), {"r": buy_rec_id}).scalar()
    db.execute(text(
        "INSERT INTO scm.reorder_recommendation (id, run_id, rec_type, product_id, status, created_at) "
        "VALUES (:id, :run, 'exception', :p, 'proposed', now())"
    ), {"id": exc_id, "run": run_id, "p": pid})
    db.flush()

    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(db, exc_id, "skip", None, [], None, [], "n/a", "tester")


# ===========================================================================
# malformed bodies
# ===========================================================================

def test_skip_with_a_quantity_is_refused(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-BADSKIP", "S16P-BADSKIP")
    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(db, rec_id, "skip", 10, [], None, [], None, "tester")


def test_no_quantity_and_not_skip_is_refused(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-BADEMPTY", "S16P-BADEMPTY")
    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(db, rec_id, "buy", None, [], None, [], None, "tester")


def test_single_kind_cannot_also_carry_another_parts_quantity(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-BADSINGLE", "S16P-BADSINGLE")
    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(db, rec_id, "buy", 10, [], 5, [], None, "tester")


def test_mixture_needs_more_than_one_part(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-BADMIX", "S16P-BADMIX")
    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(db, rec_id, "mixture", 10, [], None, [], None, "tester")


def test_unknown_kind_is_refused(scm_app):
    _, db, _, _ = scm_app
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-BADKIND", "S16P-BADKIND")
    with pytest.raises(AppException):
        dsvc.record_plan_row_decision(db, rec_id, "maybe", 10, [], None, [], None, "tester")


# ===========================================================================
# the counter feeding "N of Total made"
# ===========================================================================

def test_counter_counts_persisted_decisions(scm_app):
    _, db, _, _ = scm_app
    wid_code = "S16W-COUNT"
    wid = _mk_warehouse(db, wid_code)
    a = _mk_product(db, "S16P-COUNT-A")
    b = _mk_product(db, "S16P-COUNT-B")
    for p in (a, b):
        _mk_stock(db, p, wid, 5)
        _mk_demand(db, p, wid, 10.0)
    _link(db, a, _mk_supplier(db, "S16 Count Supplier A"), cost=60)
    _link(db, b, _mk_supplier(db, "S16 Count Supplier B"), cost=70)
    db.flush()
    run_id = _run_buys(db, wid_code)
    recs = db.execute(text(
        "SELECT id::text AS id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND rec_type = 'buy'"
    ), {"r": run_id}).mappings().all()
    assert len(recs) == 2

    before = dsvc.list_plan_row_decisions(db, run_id)
    assert before["decided_count"] == 0
    assert before["total_count"] == 2

    dsvc.record_plan_row_decision(
        db, recs[0]["id"], "buy", 20, [], None, [], None, "tester"
    )
    after = dsvc.list_plan_row_decisions(db, run_id)
    assert after["decided_count"] == 1
    assert after["total_count"] == 2
    assert after["data"][0]["recommendation_id"] == recs[0]["id"]

    dsvc.clear_plan_row_decision(db, recs[0]["id"], "tester")
    cleared = dsvc.list_plan_row_decisions(db, run_id)
    assert cleared["decided_count"] == 0


# ===========================================================================
# confirm_decisions drafts only the buy portion
# ===========================================================================

def test_confirm_decisions_drafts_only_the_buy_portion_of_a_mixture(scm_app):
    _, db, _, _ = scm_app
    run_id, rec_id, wid_code = _buy_rec(db, "S16W-CONF", "S16P-CONF")
    bin_code = "S16W-CONF-BIN"
    _mk_warehouse(db, bin_code)
    db.flush()

    dsvc.record_plan_row_decision(
        db, rec_id, "mixture", 30, [{"location": bin_code, "qty": 15}], 5, ["PO-X"],
        "partial", "tester",
    )
    out = dsvc.confirm_decisions(db, run_id, ids=None, actor="tester")
    assert out["confirmed_count"] == 1
    assert out["po_count"] == 1

    line = db.execute(text(
        "SELECT qty_ordered FROM purchase_order_lines WHERE source_ref = :r"
    ), {"r": rec_id}).mappings().first()
    assert line is not None
    # only the BUY portion (30) reaches the draft PO line — never 30+15+5
    assert float(line["qty_ordered"]) == 30


def test_confirm_decisions_drafts_nothing_for_a_use_stock_only_decision(scm_app):
    _, db, _, _ = scm_app
    run_id, rec_id, wid_code = _buy_rec(db, "S16W-CONFNONE", "S16P-CONFNONE")
    bin_code = "S16W-CONFNONE-BIN"
    _mk_warehouse(db, bin_code)
    db.flush()

    dsvc.record_plan_row_decision(
        db, rec_id, "use_stock", None, [{"location": bin_code, "qty": 12}], None, [],
        "cover from the other bin", "tester",
    )
    out = dsvc.confirm_decisions(db, run_id, ids=None, actor="tester")
    assert out["confirmed_count"] == 0
    assert out["po_count"] == 0
    line = db.execute(text(
        "SELECT qty_ordered FROM purchase_order_lines WHERE source_ref = :r"
    ), {"r": rec_id}).mappings().first()
    assert line is None


def test_plan_row_decision_takes_priority_over_legacy_accept(scm_app):
    """A rec accepted the OLD way, then decided the NEW way — the row decision is
    authoritative at confirm, so the buy qty raised is the NEW figure, not the old
    accepted rounded_qty."""
    _, db, _, _ = scm_app
    run_id, rec_id, wid_code = _buy_rec(db, "S16W-PRIORITY", "S16P-PRIORITY")

    dsvc.accept_recommendation(db, rec_id, actor="tester")
    dsvc.record_plan_row_decision(
        db, rec_id, "buy", 999, [], None, [], "the new decision wins", "tester"
    )
    out = dsvc.confirm_decisions(db, run_id, ids=None, actor="tester")
    assert out["confirmed_count"] == 1

    line = db.execute(text(
        "SELECT qty_ordered FROM purchase_order_lines WHERE source_ref = :r"
    ), {"r": rec_id}).mappings().first()
    assert float(line["qty_ordered"]) == 999


# ===========================================================================
# routes + auth
# ===========================================================================

def test_record_and_clear_via_route(scm_app):
    app, db = _client(scm_app, "purchasing")
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-ROUTE", "S16P-ROUTE")
    db.commit()

    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{rec_id}/decision",
            json={"kind": "buy", "buy_qty": 42, "reason_text": "route test"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["kind"] == "buy"
        assert body["buy_qty"] == 42

        clear_res = client.delete(f"/api/v1/scm/recommendations/{rec_id}/decision")
        assert clear_res.status_code == 200, clear_res.text
        assert clear_res.json()["cleared"] is True


def test_list_plan_row_decisions_via_route(scm_app):
    app, db = _client(scm_app, "purchasing")
    run_id, rec_id, _wid = _buy_rec(db, "S16W-LISTRT", "S16P-LISTRT")
    dsvc.record_plan_row_decision(db, rec_id, "buy", 5, [], None, [], None, "tester")
    db.commit()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{run_id}/plan-row-decisions")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["decided_count"] == 1
    assert body["total_count"] == 1
    assert body["data"][0]["recommendation_id"] == rec_id


def test_record_decision_denied_without_reorder_run_permission(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{uuid.uuid4()}/decision",
            json={"kind": "skip"},
        )
    assert res.status_code == 403


def test_clear_decision_denied_without_reorder_run_permission(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.delete(f"/api/v1/scm/recommendations/{uuid.uuid4()}/decision")
    assert res.status_code == 403


def test_list_plan_row_decisions_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)
    with TestClient(app) as client:
        res = client.get(f"/api/v1/scm/reorder-runs/{uuid.uuid4()}/plan-row-decisions")
    assert res.status_code == 403


def test_route_rejects_malformed_body(scm_app):
    app, db = _client(scm_app, "purchasing")
    _run_id, rec_id, _wid = _buy_rec(db, "S16W-MALFORMED", "S16P-MALFORMED")
    db.commit()

    with TestClient(app) as client:
        res = client.post(
            f"/api/v1/scm/recommendations/{rec_id}/decision",
            json={"kind": "skip", "buy_qty": 10},
        )
    assert res.status_code == 422, res.text
