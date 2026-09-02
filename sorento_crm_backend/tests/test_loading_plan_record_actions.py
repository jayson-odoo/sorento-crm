"""`loading_plan.cancel`, wired into the deferred-action registry (S1, AC-A7).

`tests/test_record_actions_s6b.py` owns the ENGINE-wide contract (every record action
names a known slug, declares a window its verb agrees with, its `execute` resolves).
This file owns what is specific to the loading-plan pair: cancelling a plan through
`/api/v1/pending-actions` actually flips its status when the window lapses, an
already-cancelled plan refuses the SECOND cancel at PARK time (not ten seconds later),
and `loading_plan.delete` still refuses a sent plan (existing guard, exercised here
through the SAME route the frontend now uses instead of the immediate one).

Postgres only, blank scratch schema, seeding its own chain - CI's database is empty.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.procurement import Supplier
from app.models.sla import SlaFormAction
from app.models.scm import LoadingPlan
from app.models.supplier_notice import SupplierNotice
from app.services.form_action_grace import WINDOW_REVERSIBLE, WINDOW_DESTRUCTIVE, window_class_for
from app.services.form_action_registry import REGISTRY
from tests._pg_fixture import blank_session

# `from ... import`, never `import app.services.record_actions`: the latter rebinds the
# name `app` to the PACKAGE and shadows the FastAPI instance imported above, so every
# `app.dependency_overrides` in the fixture raises AttributeError (see test_record_actions_s6b.py).
from app.services import record_actions  # noqa: F401  (registers the record actions)

BASE = "/api/v1/pending-actions"
MARKER = "ZZT-LPCANCEL"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def client(monkeypatch):
    from fastapi import Depends

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.models.user import User
    from app.services.user_service import UserPermissionService

    with blank_session() as db:

        def _override_get_db():
            yield db

        actor_row = User(
            id=_uid(), email=f"zzt-lpcancel-{_uid()[:8]}@example.test", name="Ada Actor"
        )
        db.add(actor_row)
        db.commit()
        actor = {"id": actor_row.id, "email": actor_row.email, "name": actor_row.name}

        def _override_scope(_db=Depends(get_db)):
            set_company_scope(_db, None)
            return None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: actor
        monkeypatch.setattr(
            UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True
        )
        try:
            with TestClient(app) as c:
                yield c, db, actor
        finally:
            app.dependency_overrides.clear()


def _supplier(db) -> Supplier:
    row = Supplier(
        id=_uid(), supplier_code=f"{MARKER}-{_uid()[:8]}", supplier_name=f"{MARKER} supplier"
    )
    db.add(row)
    db.commit()
    return row


def _plan(db, *, status: str = "planning", sent_at=None) -> LoadingPlan:
    supplier = _supplier(db)
    row = LoadingPlan(
        id=_uid(), supplier_id=supplier.id, status=status, sent_at=sent_at
    )
    db.add(row)
    db.commit()
    return row


def _start(c, action_key: str, entity_type: str, entity_id: str, payload=None):
    return c.post(
        BASE,
        json={
            "action_key": action_key,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "payload": payload or {},
        },
    )


def _lapse(db, action_id: str) -> None:
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def _commit_now(c, db, entity_type: str, entity_id: str, action_id: str):
    """Lapse the window and let the lazy commit on GET apply it, as a poll would."""
    _lapse(db, action_id)
    return c.get(
        f"{BASE}/current",
        params={"entity_type": entity_type, "entity_id": str(entity_id)},
    )


# --------------------------------------------------------------------------- #
# (d) the registration itself
# --------------------------------------------------------------------------- #


def test_loading_plan_cancel_is_registered_reversible_with_the_reorder_slug():
    action = REGISTRY["loading_plan.cancel"]
    assert action.entity_types == ("loading_plan",)
    assert action.window == WINDOW_REVERSIBLE
    assert window_class_for(action) == WINDOW_REVERSIBLE
    assert action.permission == "scm.reorder.run"


# --------------------------------------------------------------------------- #
# (a) parking a cancel on a planning plan, and letting the window lapse
# --------------------------------------------------------------------------- #


def test_cancel_on_a_planning_plan_parks_then_commits_to_cancelled(client):
    c, db, actor = client
    plan = _plan(db, status="planning")

    parked = _start(c, "loading_plan.cancel", "loading_plan", plan.id)
    assert parked.status_code == 202, parked.text
    assert parked.json()["window_seconds"] == 5

    db.expire_all()
    assert db.query(LoadingPlan).filter(LoadingPlan.id == plan.id).one().status == "planning"

    body = _commit_now(c, db, "loading_plan", plan.id, parked.json()["id"]).json()
    assert body["last_outcome"]["status"] == "committed", body["last_outcome"]

    db.expire_all()
    row = db.query(LoadingPlan).filter(LoadingPlan.id == plan.id).one()
    assert row.status == "cancelled"
    assert row.cancelled_at is not None
    assert row.cancelled_by == actor["name"]


def test_cancelling_in_the_toast_window_leaves_the_plan_untouched(client):
    """Cancel-the-cancel: pressing Cancel in the toast is the whole way back now that
    no confirmation dialog asks first."""
    c, db, _actor = client
    plan = _plan(db, status="planning")

    parked = _start(c, "loading_plan.cancel", "loading_plan", plan.id).json()

    response = c.post(f"{BASE}/{parked['id']}/cancel")
    assert response.status_code == 200, response.text

    db.expire_all()
    assert db.query(LoadingPlan).filter(LoadingPlan.id == plan.id).one().status == "planning"


# --------------------------------------------------------------------------- #
# (b) an already-cancelled plan refuses a second cancel AT PARK TIME
# --------------------------------------------------------------------------- #


def test_cancelling_an_already_cancelled_plan_is_refused_at_park_time(client):
    c, db, _actor = client
    plan = _plan(db, status="cancelled")

    response = _start(c, "loading_plan.cancel", "loading_plan", plan.id)

    assert response.status_code == 409, response.text
    # `app_exception_handler` (app/main.py) answers with `exc.detail` verbatim, not
    # wrapped a second time under a `detail` key the way a bare HTTPException reads.
    assert response.json()["code"] == "plan_cancelled"
    # Refused before anything was parked - no countdown to have run, nothing to undo.
    assert db.query(SlaFormAction).count() == 0


# --------------------------------------------------------------------------- #
# (c) loading_plan.delete still refuses a sent plan - through the SAME route
# --------------------------------------------------------------------------- #


def test_loading_plan_delete_is_registered_destructive():
    action = REGISTRY["loading_plan.delete"]
    assert action.window == WINDOW_DESTRUCTIVE
    assert action.permission == "scm.reorder.run"


def test_deleting_a_sent_plan_fails_the_commit_with_plan_sent(client):
    """Delete has no `capture`, so the parking half of this route's contract still
    accepts the click (the button reaching it at all would be an FE defect per AC-A5,
    which disables Delete on a sent plan) - the guard `delete_record` already owns
    fires when the window lapses, and the countdown's failure is legible by key.

    `delete_record`'s guard is `has_notices()` (a row in `supplier_notices` that WENT
    OUT), not `plan.sent_at` by itself - so the seed writes the notice, the thing the
    guard actually reads.
    """
    c, db, _actor = client
    plan = _plan(db, status="sent", sent_at=datetime.utcnow())
    db.add(SupplierNotice(id=_uid(), supplier_id=plan.supplier_id, loading_plan_id=plan.id))
    db.commit()

    parked = _start(c, "loading_plan.delete", "loading_plan", plan.id)
    assert parked.status_code == 202, parked.text

    body = _commit_now(c, db, "loading_plan", plan.id, parked.json()["id"]).json()
    assert body["last_outcome"]["status"] == "failed", body["last_outcome"]
    assert body["last_outcome"]["action_key"] == "loading_plan.delete"

    db.expire_all()
    assert db.query(LoadingPlan).filter(LoadingPlan.id == plan.id).first() is not None
