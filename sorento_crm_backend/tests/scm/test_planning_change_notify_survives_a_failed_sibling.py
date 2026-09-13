"""Review round C2: `_notify_purchasing` must run per order, INSIDE that order's own
try block - a failure on one order's confirm() must not stop the other, already-applied
order from notifying purchasing.

`_apply_one_order` loops orders and calls `supply.confirm(...)` per order (`app/services/
planning_change_service.py` ~3150); today the savepoint rollback listener that undoes a
failed order's own DB writes pops the WHOLE `Session.info` notify queue, including the
sibling order's already-queued notification, so the failure of order 2 silently eats order
1's own successful one too.

Helpers imported from `tests/test_planning_changes.py` (`api`, `_confirm`, `_line_payload`,
`_stock`, `_core_so`, `_core_line`, `_project_so`, `_project_line`, `_diff_change`) - same
world, same Postgres chain, never copied.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.models.notification import Notification
from app.models.user import User, UserRole, UserRoleAssignment, UserStatus
from app.services import planning_change_service
from app.services.project_supply_service import ProjectSupplyService
from app.services.scm.outstanding_diff import DATE_MOVED, Diff

from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    api,
    _confirm,
    _core_line,
    _core_so,
    _diff_change,
    _line_payload,
    _project_line,
    _project_so,
    _stock,
)

DELAY_PAST_WINDOW = date(2027, 3, 10)


def _seed_purchasing_user(db) -> User:
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


def test_order_1_still_notifies_purchasing_when_order_2_fails_to_apply(api, monkeypatch):
    client, world = api
    db = world.db
    _seed_purchasing_user(db)
    _stock(db, world.product, world.pool_wh, on_hand=200)

    core_so_1 = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so_1, world.product, world.own_wh, qty_ordered="40",
                              required_date=date(2026, 8, 25))
    order_1 = _project_so(db, world.project, so_id=core_so_1.id,
                           autocount_doc_no=core_so_1.so_number)
    line_1 = _project_line(db, order_1, line_no=1, product=world.product, core_line=core_line_1)

    core_so_2 = _core_so(db, world.company_id)
    core_line_2 = _core_line(db, core_so_2, world.product, world.own_wh, qty_ordered="30",
                              required_date=date(2026, 8, 25))
    order_2 = _project_so(db, world.project, so_id=core_so_2.id,
                           autocount_doc_no=core_so_2.so_number)
    line_2 = _project_line(db, order_2, line_no=1, product=world.product, core_line=core_line_2)
    db.commit()

    _confirm(client, order_1.id, {"lines": [
        _line_payload(line_1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]),
    ]})
    _confirm(client, order_2.id, {"lines": [
        _line_payload(line_2.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "30"}]),
    ]})

    changed_1 = _diff_change(
        DATE_MOVED, core_line_1, doc_number=core_so_1.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=DELAY_PAST_WINDOW, old_qty="40", new_qty="40",
    )
    changed_2 = _diff_change(
        DATE_MOVED, core_line_2, doc_number=core_so_2.so_number, item_code="ZZT-ITEM",
        location=world.own_wh.warehouse_code, old_date=date(2026, 8, 25),
        new_date=DELAY_PAST_WINDOW, old_qty="30", new_qty="30",
    )
    diff = Diff(scope_documents=(core_so_1.so_number, core_so_2.so_number),
                changes=[changed_1, changed_2])
    batch = planning_change_service.build_batch(
        db, diff,
        applied_line_ids={
            id(changed_1): str(core_line_1.id), id(changed_2): str(core_line_2.id),
        },
        order_ids={
            core_so_1.so_number: str(core_so_1.id), core_so_2.so_number: str(core_so_2.id),
        },
        actor=world.actor, import_job_id=None, file_name="book.xlsx",
    )
    db.commit()

    rows_by_order = {}
    for order_out in planning_change_service.get_batch(db, str(batch.id))["orders"]:
        rows_by_order[order_out["so_number"]] = order_out["rows"][0]["id"]
    planning_change_service.set_row_decision(
        db, str(batch.id), rows_by_order[core_so_1.so_number], "confirm",
    )
    planning_change_service.set_row_decision(
        db, str(batch.id), rows_by_order[core_so_2.so_number], "confirm",
    )
    db.commit()

    # Order 2's confirm() is made to fail - the pattern the existing failed-order tests
    # use is a real drift/status refusal; this one is monkeypatched directly, per the
    # captain's brief, so the failure is deterministic and isolated to order 2 alone.
    original_confirm = ProjectSupplyService.confirm

    def _confirm_or_raise(self, order, *args, **kwargs):
        if str(order.id) == str(order_2.id):
            raise RuntimeError("ZZT forced failure for order 2")
        return original_confirm(self, order, *args, **kwargs)

    monkeypatch.setattr(ProjectSupplyService, "confirm", _confirm_or_raise)

    result = planning_change_service.apply(db, str(batch.id), world.actor)
    db.commit()

    assert core_so_1.so_number in result["applied_orders"], result
    failed_numbers = {f["so_number"] for f in result["failed_orders"]}
    assert core_so_2.so_number in failed_numbers, result

    notifications = (
        db.query(Notification)
        .filter(Notification.source_entity_type == "planning_change_batch",
                Notification.source_entity_id == str(batch.id))
        .all()
    )
    dedup_keys = {n.dedup_key for n in notifications if getattr(n, "dedup_key", None)}
    assert f"{batch.id}:{order_1.id}:planning_change_applied" in dedup_keys, dedup_keys
    assert f"{batch.id}:{order_2.id}:planning_change_applied" not in dedup_keys, dedup_keys
