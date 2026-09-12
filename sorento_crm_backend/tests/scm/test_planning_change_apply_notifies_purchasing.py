"""Confirm-all must not die when a purchasing-role user actually exists to be notified.

Found while chasing an unrelated B1 reviewer finding
(`documentation/plans/scm/PLAN-scm-board-picks-up-pending-change.md`): a diagnostic that
seeded a `purchasing`-role user turned BOTH orders' confirm-all results into `"This
transaction is closed"`, regardless of the B1 guard under test there. Live has
purchasing-role users (`_purchasing_user_ids()`,
`app/services/project_order_inquiry_service.py` ~1813, resolves everyone holding the
`purchasing` role slug via `UserRoleAssignment` -> `UserRole.slug == "purchasing"`, active,
not trashed), so if applying a batch dies the moment one exists, the feature is broken on
live, not only in a scratch-schema fixture with no purchasing user in it - which is why
every OTHER planning-change test in this codebase (grepped `purchasing` across `tests/`)
never seeded the role and so never exercised this path at all.

`_notify_purchasing` (`app/services/planning_change_service.py` ~2238) calls
`NotificationService.create_with_channel_preferences` once per purchasing user, with
`dedup_key=f"{batch.id}:{order.id}:planning_change_applied"`, `source_entity_type=
"planning_change_batch"`, `source_entity_id=str(batch.id)` - inside `apply()`'s per-order
try block, so its own docstring's "best-effort - a notify failure must not undo a written
plan" is the claim this test holds it to.

Helpers are imported from `tests/test_planning_changes.py` (`api`, `_confirm`,
`_line_payload`, `_stock`) and `tests/scm/test_planning_change_gate_held_or_inquiry.py`
(`_adopted_line`, `_build`, `_change`) - same world, same Postgres chain, never copied.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.notification import Notification
from app.models.planning_change import (
    PLANNING_CHANGE_STATE_APPLIED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.user import User, UserRole, UserRoleAssignment, UserStatus
from app.services.scm.outstanding_diff import DATE_MOVED

from tests.scm.test_planning_change_gate_held_or_inquiry import _adopted_line, _build, _change
from tests.test_planning_changes import BASE, _confirm, _line_payload, _stock, api  # noqa: F401

DELAY_PAST_WINDOW = date(2027, 3, 10)


def _seed_purchasing_user(db) -> User:
    """Exactly what `_purchasing_user_ids()` resolves: a role whose `slug == 'purchasing'`,
    an ACTIVE, not-trashed `User`, and the `UserRoleAssignment` joining them."""
    role = UserRole(
        id=str(uuid.uuid4()), slug="purchasing",
        name=f"ZZT Purchasing {uuid.uuid4().hex[:6]}",
    )
    db.add(role)
    db.flush()
    user = User(
        id=str(uuid.uuid4()), email=f"zzt-purchasing-{uuid.uuid4().hex[:6]}@zzt.test",
        name="ZZT Purchasing", status=UserStatus.ACTIVE.value, is_trashed=False,
    )
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=user.id, role_id=role.id))
    db.flush()
    return user


def test_confirm_all_applies_the_batch_and_notifies_purchasing_without_dying(api):
    client, world = api
    db = world.db
    purchasing_user = _seed_purchasing_user(db)

    _stock(db, world.product, world.pool_wh, on_hand=200)
    a_so, a_core, a_order, a_line = _adopted_line(db, world, qty="40")
    a_payload = _line_payload(
        a_line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}],
    )
    _confirm(client, a_order.id, {"lines": [a_payload]})
    change = _change(
        DATE_MOVED, a_so, a_core, old_qty="40", new_qty="40", new_date=DELAY_PAST_WINDOW,
    )
    a_batch = _build(db, world, a_so, [(change, a_core)])
    db.commit()

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={
        "orders": [{"pso_id": a_order.id, "lines": [a_payload], "batch_id": str(a_batch.id)}],
    })

    assert response.status_code == 200, response.text
    a_result = response.json()["results"][0]
    assert "transaction is closed" not in (a_result.get("error") or "").lower(), a_result
    assert a_result["ok"] is True, a_result

    db.expire_all()
    a_row = db.query(PlanningChangeRow).filter_by(batch_id=a_batch.id).one()
    assert a_row.applied_state == PLANNING_CHANGE_STATE_APPLIED, a_row.applied_state
    reloaded_batch = db.get(PlanningChangeBatch, a_batch.id)
    assert reloaded_batch.applied_at is not None

    dedup_key = f"{a_batch.id}:{a_order.id}:planning_change_applied"
    notifications = (
        db.query(Notification)
        .filter_by(user_id=purchasing_user.id, dedup_key=dedup_key)
        .all()
    )
    assert len(notifications) == 1, notifications
