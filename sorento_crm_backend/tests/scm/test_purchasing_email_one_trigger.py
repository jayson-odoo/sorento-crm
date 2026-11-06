"""FP-EMAIL-ONE-TRIGGER: the purchasing email has one trigger, the board Confirm.

Owner ruling 6 Nov 2026: "I only want the email to purchasing to have 1 trigger, which is this
button" (Fulfilment Planning, "Confirm N orders"). Plan + behaviour card:
`documentation/plans/fulfilment/PLAN-email-one-trigger-6nov.md`.

The gate is structural: `mark_purchasing_email_trigger` marks the ROOT transaction of a press that
may email purchasing (the board Confirm; Publish amendment, the owner's Q4 exception), and the
post-commit drain sends the handover only for a marked transaction. K4 (a planning-change batch
the board Confirm applies) still emails; the same apply anywhere else emails nobody. S1 (AutoCount
ingest) lives beside its siblings in `tests/test_ac_removed_lines_ingest.py`.

Postgres only, every FK seeded by the `api` fixture of `tests/test_planning_changes.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

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


def test_k4_a_batch_applied_by_the_board_confirm_emails_purchasing(api, monkeypatch):
    """K4: the board's Confirm on a `?batch=` board marks its transaction before the apply:
    one handover email, as before."""
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    mark_purchasing_email_trigger(world.db)
    planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()

    assert len(_handover_calls(calls)) == 1, [c["trigger_type"] for c in calls]


def test_the_same_apply_outside_a_trigger_emails_nobody(api, monkeypatch):
    """The gate, not the caller, decides: an apply with no trigger around it changes the rows
    and queues their lines, but the drain sends no handover and no changed-with-links."""
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()

    oi_mail = [
        c["trigger_type"]
        for c in calls
        if c["trigger_type"] in ("order_inquiry_handover", "order_inquiry_changed_with_links")
    ]
    assert oi_mail == [], oi_mail


def test_s2_the_standalone_apply_route_is_gone(api):
    """Q2 (owner, 6 Nov 2026): no more AutoCount SO book uploads, so the standalone Apply route
    is deleted; the board Confirm is what applies a batch."""
    client, world = api
    batch = _amended_batch(client, world)

    response = client.post(f"{BASE}/planning-changes/{batch.id}/apply")

    assert response.status_code in (404, 405), response.text


def test_a_mark_ends_with_its_transaction(api, monkeypatch):
    """The mark is per root transaction: a later, unmarked write on the same session is not
    sent on an earlier trigger's account."""
    from app.services.project_order_inquiry_service import (
        _PURCHASING_TRIGGER_TX_KEY,
        mark_purchasing_email_trigger,
    )

    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    batch = _amended_batch(client, world)
    calls.clear()

    mark_purchasing_email_trigger(world.db)
    world.db.rollback()
    assert not world.db.info.get(_PURCHASING_TRIGGER_TX_KEY)

    planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()

    assert _handover_calls(calls) == [], [c["trigger_type"] for c in calls]


def test_q4_publish_amendment_marks_its_transaction(monkeypatch):
    """Q4 (owner, 6 Nov 2026): Publish amendment keeps its purchasing email, so its route marks
    the transaction the publish runs in. The services are stubbed: what is pinned is that the
    mark is on when `publish_amendment` writes."""
    from app.api.v1.projects import sales_orders as route
    from app.services.project_order_inquiry_service import _may_email_purchasing

    from tests._pg_fixture import blank_session

    seen = {}

    class _Delta:
        def __init__(self, db):
            self.db = db

        def get_amendment(self, amendment_id):
            return {"project_sales_order_id": "pso"}

        def publish_amendment(self, amendment_id, *, actor_user_id):
            seen["marked"] = _may_email_purchasing(self.db)
            return {"status": "published"}

    class _Draft:
        def __init__(self, db):
            pass

        def get_order(self, pso_id):
            return SimpleNamespace(project_id="project")

    monkeypatch.setattr(route, "ProjectSODeltaService", _Delta)
    monkeypatch.setattr(route, "ProjectSODraftService", _Draft)
    monkeypatch.setattr(route, "permission_slugs", lambda db, user_id: set())
    monkeypatch.setattr(route.projects, "get_project_or_404", lambda db, pid: object())
    monkeypatch.setattr(route.projects, "assert_can_write_project", lambda *a, **k: None)

    with blank_session() as db:
        body = route.publish_amendment(
            "00000000-0000-0000-0000-000000000001", current_user={"id": "u"}, db=db
        )

    assert body == {"status": "published"}
    assert seen["marked"] is True
