"""A deferred `Set company...` on a folder must not be falsely marked
committed by a process that does not know the action key (S6,
shared-brand-attachments R22).

Reproduces the S2 browser finding: the FE reported "Company set" for a folder
going Shared, but a hard reload showed the folder still owned. Traced against
the live `:8100` worktree server (no browser): a folder was created, the
FE's exact `POST /api/v1/pending-actions` body was sent
(`action_key=attachment_directory.set_company`,
`entity_type=attachment_directory`, `payload={"company_id": null}`), the
window was let lapse for real, and the `sla_form_actions` row read back
`status=committed` with `committed_at` set - while the folder's `company_id`
in Postgres never changed. `AttachmentCompanyService.apply()` itself is
correct (a direct call nulls the column); the defect is in
`FormActionService.commit_one`, which claims the row (raw UPDATE to
`status=COMMITTED`) *before* resolving the handler via `action_for()`. Any
process sharing the same `sla_form_actions` table that does not have this key
registered - a sibling dev worktree on an older branch racing the same
Postgres via its own `form_action_commit` scheduler tick, or (in principle)
any process one deploy behind - raises `KeyError` from `action_for()` after
the claim already committed, and the row is left permanently `committed`
with the folder untouched and no `error_text` for the reader.

Postgres only via `tests/_pg_fixture.py::blank_session`, own `ZZT-` folder -
CI's database is empty, nothing borrowed from an existing row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.resources import AttachmentDirectory
from app.models.sla import FORM_ACTION_COMMITTED, FORM_ACTION_PENDING, SlaFormAction
from app.models.user import User

from tests import _shared_brand_seed as seed
from tests._pg_fixture import blank_session

SORENTO = seed.SORENTO_ID
BASE = "/api/v1/pending-actions"
ACTION_KEY = "attachment_directory.set_company"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def client():
    from fastapi import Depends

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        actor = User(id=_uid(), email=f"zzt-actor-{_uid()[:8]}@example.test", name="Ada Actor")
        db.add(actor)
        db.commit()
        actor_dict = {"id": actor.id, "email": actor.email, "name": actor.name}

        def _override_get_db():
            yield db

        def _override_scope(_db=Depends(get_db)):
            # This test is about the commit race, not about scope visibility.
            set_company_scope(_db, None)
            return None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: actor_dict
        try:
            with TestClient(app) as c:
                yield c, db, actor_dict
        finally:
            app.dependency_overrides.clear()


def _lapse(db, action_id: str) -> None:
    """Move the window into the past without waiting out the real grace period."""
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def test_a_rival_process_without_the_action_key_must_not_falsely_commit_the_row(client):
    """The exact FE body `SetCompanyDialog` + `pendingActionService.createPendingAction`
    send for a folder going Shared."""
    c, db, _actor = client
    from app.services.form_action_registry import REGISTRY
    from app.services.form_action_service import FormActionService

    folder = seed.folder(db, company_id=SORENTO, name="ZZT-race-folder")
    db.commit()

    resp = c.post(
        BASE,
        json={
            "action_key": ACTION_KEY,
            "entity_type": "attachment_directory",
            "entity_id": folder.id,
            "payload": {"company_id": None},
        },
    )
    assert resp.status_code == 202, resp.text
    action_id = resp.json()["id"]
    _lapse(db, action_id)

    # Simulate a rival scheduler process sharing this Postgres table but
    # running a registry that has never heard of this key - the exact shape
    # of "another worktree's backend races the same sla_form_actions row",
    # reproduced live against the :8100 worktree server.
    saved = REGISTRY.pop(ACTION_KEY)
    try:
        FormActionService(db).commit_due()
    finally:
        REGISTRY[ACTION_KEY] = saved

    db.expire_all()
    row = db.query(SlaFormAction).filter(SlaFormAction.id == action_id).one()
    still_owned = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == folder.id).one()

    # A process that cannot resolve the handler must leave the row exactly as
    # it found it - PENDING - so a process that DOES know the key (the next
    # sweep here, or another process) still gets to run it. Never COMMITTED
    # for work that never ran: that is a silent, permanent no-op, because
    # `status != PENDING` means no sweep will ever look at this row again.
    assert row.status == FORM_ACTION_PENDING, (
        f"row was marked {row.status!r} by a process that never executed the "
        "action - the folder's company_id is now stuck forever"
    )
    assert still_owned.company_id == SORENTO, "must be untouched until a process that knows the key runs it"

    # The same row, worked by a process that DOES have the key - the eventual
    # success case (S6-08, the sweeper picks up whoever is not watching).
    outcome = FormActionService(db).commit_due()
    assert outcome["committed"] >= 1

    db.expire_all()
    row = db.query(SlaFormAction).filter(SlaFormAction.id == action_id).one()
    shared = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == folder.id).one()
    assert row.status == FORM_ACTION_COMMITTED
    assert shared.company_id is None, "Set company -> Shared must actually null the folder's company_id"
