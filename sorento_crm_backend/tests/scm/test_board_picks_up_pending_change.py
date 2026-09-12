"""The fulfilment board picks up a pending planning change on its own.

`documentation/plans/scm/PLAN-scm-board-picks-up-pending-change.md`, AC-B1, AC-B5, AC-B7
backend halves, plus the helper contract the plan lifts out of
`SalesOrderService.with_planning_changes`.

Helpers are imported from `tests/test_planning_changes.py` (world, `api`, `_confirm`,
`_line_payload`, `_stock`, `_diff_change`) and from the already-committed
`tests/scm/test_planning_change_gate_held_or_inquiry.py` (`_adopted_line`, `_build`,
`_change`) - same world, same Postgres chain, never copied.

A held line delayed past the reserve window (`new_date=date(2027, 3, 10)`) always suggests
`release` (`planning_change_service.suggest`, rule 2), which `_build_row` pre-sets to
`decision="accept"` - so these batches apply with an EMPTY `lines` list on the confirm
call, exactly like `tests/test_planning_changes.py::test_apply_release_returns_the_whole_
line_to_the_board_with_no_buy_and_no_oi_change` does through `apply()` directly.
"""
from __future__ import annotations

from datetime import date

from app.models.planning_change import (
    PLANNING_CHANGE_STATE_APPLIED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.services import planning_change_service
from app.services.scm.outstanding_diff import DATE_MOVED
from app.services.scm.sales_order_service import SalesOrderService

from tests.scm.test_planning_change_gate_held_or_inquiry import _adopted_line, _build, _change
from tests.test_planning_changes import BASE, _confirm, _line_payload, _stock, api  # noqa: F401

DELAY_PAST_WINDOW = date(2027, 3, 10)


def _held_release_batch(client, world, *, qty: str, line_no: int = 1):
    """One adopted, held (full reserve) line, delayed past the window - a pending batch
    whose only row is a pre-accepted `release` (see module docstring)."""
    db = world.db
    so, core_line, order, line = _adopted_line(db, world, qty=qty, line_no=line_no)
    reserve_payload = _line_payload(
        line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": qty}],
    )
    _confirm(client, order.id, {"lines": [reserve_payload]})
    change = _change(
        DATE_MOVED, so, core_line, old_qty=qty, new_qty=qty, new_date=DELAY_PAST_WINDOW,
    )
    batch = _build(db, world, so, [(change, core_line)])
    db.commit()
    return so, core_line, order, line, batch, reserve_payload


# --------------------------------------------------------------------------- #
# AC-B1: the board names the batch on `orders[]`, with no `batch=` param
# --------------------------------------------------------------------------- #


def test_ac_b1_board_names_pending_batch_null_when_none_or_applied(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)

    a_so, _a_core, _a_order, _a_line, a_batch, _a_payload = _held_release_batch(
        client, world, qty="40",
    )

    b_so, _b_core, _b_order, _b_line = _adopted_line(db, world, qty="10")
    db.commit()

    c_so, _c_core, _c_order, _c_line, c_batch, _c_payload = _held_release_batch(
        client, world, qty="20",
    )
    planning_change_service.apply(db, str(c_batch.id), world.actor)
    db.commit()

    orders_param = ",".join([a_so.so_number, b_so.so_number, c_so.so_number])
    response = client.get(f"{BASE}/fulfilment-planning/board", params={"orders": orders_param})
    assert response.status_code == 200, response.text
    by_so = {o["so_number"]: o for o in response.json()["orders"]}

    assert by_so[a_so.so_number].get("pending_change_batch_id") == str(a_batch.id)
    assert by_so[b_so.so_number].get("pending_change_batch_id") is None
    assert by_so[c_so.so_number].get("pending_change_batch_id") is None


# --------------------------------------------------------------------------- #
# AC-B7 backend half: the fulfilment-planning LIST row carries the same id
# --------------------------------------------------------------------------- #


def test_ac_b7_list_row_carries_pending_batch_id(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)

    a_so, _a_core, _a_order, _a_line, a_batch, _a_payload = _held_release_batch(
        client, world, qty="40",
    )
    b_so, _b_core, _b_order, _b_line = _adopted_line(db, world, qty="10")
    db.commit()

    resp_a = client.get(f"{BASE}/fulfilment-planning", params={"sales_order_id": a_so.id})
    assert resp_a.status_code == 200, resp_a.text
    rows_a = resp_a.json()["data"]
    assert rows_a, "expected the adopted order to appear on the worklist"
    assert rows_a[0].get("planning_change_batch_id") == str(a_batch.id)

    resp_b = client.get(f"{BASE}/fulfilment-planning", params={"sales_order_id": b_so.id})
    assert resp_b.status_code == 200, resp_b.text
    rows_b = resp_b.json()["data"]
    assert rows_b, "expected the adopted order to appear on the worklist"
    assert rows_b[0].get("planning_change_batch_id") is None


# --------------------------------------------------------------------------- #
# AC-B5: confirm-all carries `batch_id` per order
# --------------------------------------------------------------------------- #


def test_ac_b5_per_order_batch_id_applies_only_that_orders_batch(api):
    """(a) a per-order `batch_id`, no body-level one, applies that order's batch.
    (c) a sibling order in the SAME call with no `batch_id` at all still confirms as an
    ordinary revision, and touches no planning-change row."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)

    a_so, _a_core, a_order, _a_line, a_batch, a_payload = _held_release_batch(
        client, world, qty="40",
    )

    b_so, _b_core, b_order, b_line = _adopted_line(db, world, qty="15")
    b_payload = _line_payload(
        b_line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "15"}],
    )

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={
        "orders": [
            {"pso_id": a_order.id, "lines": [a_payload], "batch_id": str(a_batch.id)},
            {"pso_id": b_order.id, "lines": [b_payload]},
        ],
    })
    assert response.status_code == 200, response.text

    db.expire_all()
    a_row = db.query(PlanningChangeRow).filter_by(batch_id=a_batch.id).one()
    a_batch_reloaded = db.get(PlanningChangeBatch, a_batch.id)
    assert a_row.applied_state == PLANNING_CHANGE_STATE_APPLIED, a_row.applied_state
    assert a_batch_reloaded.applied_at is not None

    results_by_pso = {r["pso_id"]: r for r in response.json()["results"]}
    assert results_by_pso[str(b_order.id)]["ok"] is True, results_by_pso[str(b_order.id)]
    assert db.query(PlanningChangeRow).filter_by(
        project_sales_order_id=str(b_order.id)
    ).count() == 0


def test_ac_b5_body_level_batch_id_old_shape_still_applies(api):
    """(b) regression guard: the pre-slice shape (`batch_id` on the BODY, applying to
    every order named) must keep working during the deploy window."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)

    so, _core, order, _line, batch, payload = _held_release_batch(client, world, qty="40")

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={
        "orders": [{"pso_id": order.id, "lines": [payload]}],
        "batch_id": str(batch.id),
    })
    assert response.status_code == 200, response.text

    db.expire_all()
    row = db.query(PlanningChangeRow).filter_by(batch_id=batch.id).one()
    reloaded_batch = db.get(PlanningChangeBatch, batch.id)
    assert row.applied_state == PLANNING_CHANGE_STATE_APPLIED, row.applied_state
    assert reloaded_batch.applied_at is not None


# --------------------------------------------------------------------------- #
# Helper contract: `planning_change_service.pending_batch_id_by_sales_order`
# --------------------------------------------------------------------------- #


def test_pending_batch_id_by_sales_order_returns_newest_pending_and_omits_the_rest(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)

    a_so, _a_core, _a_order, _a_line, a_batch, _a_payload = _held_release_batch(
        client, world, qty="40",
    )
    b_so, _b_core, _b_order, _b_line = _adopted_line(db, world, qty="10")
    db.commit()
    c_so, _c_core, _c_order, _c_line, c_batch, _c_payload = _held_release_batch(
        client, world, qty="20",
    )
    planning_change_service.apply(db, str(c_batch.id), world.actor)
    db.commit()

    result = planning_change_service.pending_batch_id_by_sales_order(
        db, [a_so.id, b_so.id, c_so.id],
    )
    assert result == {str(a_so.id): str(a_batch.id)}


def test_with_planning_changes_regression_guard_still_returns_the_batch_id(api):
    """The refactor lifts the body of `SalesOrderService.with_planning_changes` into the
    helper above; this pins that the SCM list's own pill is unaffected by the move."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)

    so, _core, _order, _line, batch, _payload = _held_release_batch(client, world, qty="40")

    rows = SalesOrderService(db).with_planning_changes([{"id": str(so.id)}])
    assert rows[0]["planning_change_batch_id"] == str(batch.id)


# --------------------------------------------------------------------------- #
# B1 (blocker, reviewer's pass on 39a5d8b07): body-level batch_id must not
# override an order's own EXPLICIT null when the body mixes both shapes - the
# shape the current frontend sends when the board has loaded exactly one batch
# (`FulfilmentBoardPanel.tsx`'s confirmMany call still sends `batch_id` on the
# body alongside per-order `batch_id`s). `entry.batch_id or payload.batch_id`
# cannot tell "B legitimately has none" from "B did not say", so it silently
# tries to apply batch X against order B, which holds no rows of it.
# --------------------------------------------------------------------------- #


def _seed_mixed_batch_and_ordinary_orders(client, world):
    """Order A: pending batch X (held, release). Order B: an ordinary, undecided,
    adopted line with nothing to do with X - a ready-to-confirm reserve."""
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)
    a_so, _a_core, a_order, _a_line, a_batch, a_payload = _held_release_batch(
        client, world, qty="40",
    )
    b_so, _b_core, b_order, b_line = _adopted_line(db, world, qty="15", line_no=2)
    b_payload = _line_payload(
        b_line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "15"}],
    )
    return a_order, a_batch, a_payload, b_order, b_payload


def _assert_a_applied_b_ordinary(db, a_order, a_batch, b_order, response):
    from app.models.project_so import SOSupplyDecision

    assert response.status_code == 200, response.text
    results_by_pso = {r["pso_id"]: r for r in response.json()["results"]}

    a_result = results_by_pso[str(a_order.id)]
    assert a_result["ok"] is True, a_result

    b_result = results_by_pso[str(b_order.id)]
    assert b_result["ok"] is True, b_result
    assert "already applied" not in (b_result.get("error") or ""), b_result

    db.expire_all()
    a_row = db.query(PlanningChangeRow).filter_by(batch_id=a_batch.id).one()
    assert a_row.applied_state == PLANNING_CHANGE_STATE_APPLIED, a_row.applied_state

    assert db.query(PlanningChangeRow).filter_by(
        project_sales_order_id=str(b_order.id)
    ).count() == 0

    b_decisions = (
        db.query(SOSupplyDecision).filter_by(project_sales_order_id=b_order.id).count()
    )
    assert b_decisions >= 1, "expected an ordinary supply decision for order B"


def test_b1_mixed_body_and_per_order_batch_id_a_first(api):
    """A named first in `orders`, matching the body-level `batch_id`; B follows with an
    explicit per-order `batch_id: null`."""
    client, world = api
    db = world.db
    a_order, a_batch, a_payload, b_order, b_payload = _seed_mixed_batch_and_ordinary_orders(
        client, world,
    )

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={
        "orders": [
            {"pso_id": a_order.id, "lines": [a_payload], "batch_id": str(a_batch.id)},
            {"pso_id": b_order.id, "lines": [b_payload], "batch_id": None},
        ],
        "batch_id": str(a_batch.id),
    })
    _assert_a_applied_b_ordinary(db, a_order, a_batch, b_order, response)


def test_b1_mixed_body_and_per_order_batch_id_b_first(api):
    """Same body, orders REVERSED - the reviewer's finding was order-dependent, so both
    sequences are pinned rather than just the one that happened to be tried first."""
    client, world = api
    db = world.db
    a_order, a_batch, a_payload, b_order, b_payload = _seed_mixed_batch_and_ordinary_orders(
        client, world,
    )

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={
        "orders": [
            {"pso_id": b_order.id, "lines": [b_payload], "batch_id": None},
            {"pso_id": a_order.id, "lines": [a_payload], "batch_id": str(a_batch.id)},
        ],
        "batch_id": str(a_batch.id),
    })
    _assert_a_applied_b_ordinary(db, a_order, a_batch, b_order, response)
