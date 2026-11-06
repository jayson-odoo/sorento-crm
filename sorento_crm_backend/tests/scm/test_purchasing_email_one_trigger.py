"""FP-EMAIL-ONE-TRIGGER: the purchasing email has exactly one trigger, the board Confirm.

Owner ruling 6 Nov 2026: "I only want the email to purchasing to have 1 trigger, which is this
button" (Fulfilment Planning, "Confirm N orders"). Plan + behaviour card:
`documentation/plans/fulfilment/PLAN-email-one-trigger-6nov.md`.

The gate is structural: `mark_board_confirm` marks the ROOT transaction a board Confirm runs in,
and the post-commit drains send the purchasing handover only for a marked transaction. These tests
pin K4 (a planning-change batch applied BY the board Confirm still emails) against S2 (the same
apply from the standalone route emails nothing). S1 (AutoCount ingest) lives beside its siblings in
`tests/test_ac_removed_lines_ingest.py`.

Postgres only, every FK seeded by the `api` fixture of `tests/test_planning_changes.py`.
"""
from __future__ import annotations

from app.services import planning_change_service

from tests.scm.test_oi_closed_line import _amend_to
from tests.test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)
from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    BASE,
    _held_line_advanced_replan_row,
    _line_payload,
    _stock,
    api,
)


def _amended_batch(client, world):
    """A confirmed Buy 72 line whose date moved, amended to Reserve 72 at the pool: applying
    it cancels the raised ORDER row, which the handover tells purchasing as a change."""
    _stock(world.db, world.product, world.pool_wh, on_hand=100)
    batch, order, line, row = _held_line_advanced_replan_row(client, world)
    _amend_to(client, batch, row, _line_payload(
        line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "72"}],
        amend_reason="Use BRW, the pool has it.",
    ))
    world.db.commit()
    return batch


def test_k4_a_batch_applied_inside_the_board_confirm_emails_purchasing(api, monkeypatch):
    """K4: the board's Confirm on a `?batch=` board marks its transaction before the apply: one
    handover email, as before."""
    from app.services.project_order_inquiry_service import mark_board_confirm

    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    mark_board_confirm(world.db)
    planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()

    assert len(_handover_calls(calls)) == 1, [c["trigger_type"] for c in calls]


def test_s2_the_standalone_apply_route_emails_nobody(api, monkeypatch):
    """S2: `POST /planning-changes/{id}/apply` is not the board Confirm. The batch still
    applies; purchasing gets no handover and no changed-with-links email."""
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")

    assert response.status_code == 200, response.text
    oi_mail = [
        c["trigger_type"]
        for c in calls
        if c["trigger_type"] in ("order_inquiry_handover", "order_inquiry_changed_with_links")
    ]
    assert oi_mail == [], oi_mail


def test_s2_the_same_apply_outside_any_scope_emails_nobody(api, monkeypatch):
    """The gate, not the route, decides: a service call with no board Confirm around it
    queues lines but the drain sends nothing."""
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()

    assert _handover_calls(calls) == [], [c["trigger_type"] for c in calls]


def test_a_rolled_back_mark_leaves_no_mark_behind(api, monkeypatch):
    """The mark is per root transaction: a later, unscoped write on the same session is not
    sent on an earlier Confirm's account."""
    from app.services.project_order_inquiry_service import (
        _BOARD_CONFIRM_TX_KEY,
        mark_board_confirm,
    )

    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    mark_board_confirm(world.db)
    world.db.rollback()
    assert not world.db.info.get(_BOARD_CONFIRM_TX_KEY)

    planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()

    assert _handover_calls(calls) == [], [c["trigger_type"] for c in calls]
