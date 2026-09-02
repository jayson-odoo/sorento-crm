"""Tag template list bulk delete (PLAN-price-tag-feedback-r2.md D26, S11).

UAC:
  AC-S11-1 [FE] Selected rows delete via the deferred-action pattern, Undo
      toast, no confirmation dialog - `TagTemplatesList.test.tsx`'s job.
  AC-S11-2 [BE] `tag_template.bulk_delete` deletes only templates in the
      caller's company scope; a foreign id in the batch refuses the WHOLE
      batch with one 404 (no existence oracle). Owned here.

`tag_template_service.bulk_delete` covers the atomicity rule directly (no
existence oracle: a foreign id and a missing id read exactly the same). The
`/pending-actions` route tests below cover the deferred half: nothing is
deleted until the window lapses, permission is enforced before parking, and
the batch's own countdown carries every selected id.

Fixture mirrors `test_dealer_kit_tag_template_versions.py` (real company
scope, not the S6b bypass - AC-S11-2 is a company-scope test).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.dealer_kit import TagTemplate
from app.models.sla import SlaFormAction
from app.services import record_actions  # noqa: F401  (registers tag_template.bulk_delete)
from app.services.dealer_kit import tag_template_service
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_MANAGER_ID = "6f7a8b9c-0d1e-561f-3a7b-8c9d0e1f2a63"
_MANAGER_ROLE = "7a8b9c0d-1e2f-572a-4b8c-9d0e1f2a3b74"
_VIEWER_ID = "8b9c0d1e-2f3a-583b-5c9d-0e1f2a3b4c85"
_VIEWER_ROLE = "9c0d1e2f-3a4b-594c-6d0e-1f2a3b4c5d96"


def _doc(width=85, height=58):
    return {"layers": [], "width_mm": width, "height_mm": height}


def _seed_roles(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slugs = ("dealer_kit.tag_templates.view", "dealer_kit.tag_templates.manage")
    perm_ids: dict[str, str] = {}
    for slug in slugs:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        perm_ids[slug] = perm_id
    db.flush()

    roles = (
        (_MANAGER_ROLE, "zzt_ttd_manager", _MANAGER_ID, slugs),
        (_VIEWER_ROLE, "zzt_ttd_viewer", _VIEWER_ID, (slugs[0],)),
    )
    for role_id, slug, user_id, granted in roles:
        db.add(
            UserRole(
                id=role_id, slug=slug, name=slug, description="",
                is_protected=False, is_default=False,
            )
        )
        db.add(User(id=user_id, email=f"{slug}@test.com", name=slug, status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for granted_slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_ids[granted_slug]
                )
            )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        _as(_MANAGER_ID)
        yield db, _as, _in_company

        app.dependency_overrides.clear()


def _create_template(client: TestClient, name: str | None = None) -> str:
    res = client.post(
        "/api/v1/dealer-kit/tag-templates",
        json={
            "name": name or unique_code("Tmpl"),
            "family": "toilet",
            "doc": _doc(),
            "print_size": {"width_mm": 85, "height_mm": 58},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------- #
# Service-level: the atomicity rule itself (AC-S11-2)
# --------------------------------------------------------------------------- #


def test_bulk_delete_removes_every_row_in_scope(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        a = _create_template(client)
        b = _create_template(client)

    out = tag_template_service.bulk_delete(db, [a, b])

    assert out == {"deleted": 2}
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id.in_([a, b])).count() == 0


def test_a_missing_id_refuses_the_whole_batch(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        a = _create_template(client)

    with pytest.raises(AppException) as exc:
        tag_template_service.bulk_delete(db, [a, str(uuid.uuid4())])

    assert exc.value.status_code == 404
    db.expire_all()
    # The one real id in the batch is UNTOUCHED - a partial delete would be a
    # data-loss surprise nobody selected on purpose.
    assert db.query(TagTemplate).filter(TagTemplate.id == a).first() is not None


def test_a_foreign_companys_id_reads_exactly_like_a_missing_one(api):
    """No existence oracle: refusing a batch must not tell the caller WHICH
    id was the problem, or whether it exists somewhere else."""
    from app.models.company import Company

    db, _as, _scope = api

    with TestClient(app) as client:
        mine = _create_template(client)

    other_company = str(uuid.uuid4())
    db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
    db.commit()
    _scope(other_company)
    with TestClient(app) as client:
        theirs = _create_template(client)
    _scope(_SORENTO)

    missing_id_exc = None
    try:
        tag_template_service.bulk_delete(db, [mine, str(uuid.uuid4())])
    except AppException as exc:
        missing_id_exc = exc

    foreign_id_exc = None
    try:
        tag_template_service.bulk_delete(db, [mine, theirs])
    except AppException as exc:
        foreign_id_exc = exc

    assert missing_id_exc is not None and foreign_id_exc is not None
    # Same status, same message, whether the id is missing outright or simply
    # belongs to someone else - there is nothing here for a caller to learn
    # about which one it was.
    assert missing_id_exc.status_code == foreign_id_exc.status_code == 404
    assert missing_id_exc.detail["message"] == foreign_id_exc.detail["message"]
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id == mine).first() is not None
    _scope(other_company)
    assert db.query(TagTemplate).filter(TagTemplate.id == theirs).first() is not None


# --------------------------------------------------------------------------- #
# Route-level: the deferred half (parking, window, permission)
# --------------------------------------------------------------------------- #

BASE = "/api/v1/pending-actions"


def _start(c, ids, entity_id: str | None = None):
    """Park the batch. `entity_id` is a fresh token per click - the FE's own
    (`crypto.randomUUID()`), not a real template - so every batch gets its own
    countdown regardless of which ids it names. Defaults to a random one;
    callers that need to poll `/current` afterwards pass their own."""
    return c.post(
        BASE,
        json={
            "action_key": "tag_template.bulk_delete",
            "entity_type": "tag_template",
            "entity_id": entity_id or str(uuid.uuid4()),
            "payload": {"template_ids": ids},
        },
    )


def _lapse(db, action_id: str) -> None:
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def test_happy_path_parks_then_deletes_on_window_lapse(api):
    """Nothing is deleted while the window is open (S6-01) - the "action fires
    only after the toast window" half of the contract - and the commit, once
    it runs (the lazy commit `GET /current` performs, same as a real poll),
    takes every id in the batch."""
    db, _as, _scope = api

    batch_id = str(uuid.uuid4())
    with TestClient(app) as client:
        a = _create_template(client)
        b = _create_template(client)

        parked = _start(client, [a, b], entity_id=batch_id)
        assert parked.status_code == 202, parked.text
        assert parked.json()["window_seconds"] == 10

        db.expire_all()
        assert db.query(TagTemplate).filter(TagTemplate.id.in_([a, b])).count() == 2

        _lapse(db, parked.json()["id"])
        current = client.get(
            f"{BASE}/current",
            params={"entity_type": "tag_template", "entity_id": batch_id},
        )

    assert current.status_code == 200, current.text
    assert current.json()["last_outcome"]["status"] == "committed"
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id.in_([a, b])).count() == 0


def test_a_foreign_id_in_the_parked_batch_fails_the_whole_batch_at_commit(api):
    """The park itself always answers 202 (UI channel defers); the atomicity
    rule surfaces at commit, in `last_outcome` - read through the SAME route
    the countdown polls, exactly like every other premise failure this engine
    has (`test_a_delete_blocked_by_a_foreign_key_says_so_without_showing_the_
    sql` in test_record_actions_s6b.py)."""
    db, _as, _scope = api

    with TestClient(app) as client:
        a = _create_template(client)

    batch_id = str(uuid.uuid4())
    with TestClient(app) as client:
        parked = _start(client, [a, str(uuid.uuid4())], entity_id=batch_id)
        assert parked.status_code == 202, parked.text

        _lapse(db, parked.json()["id"])

        current = client.get(
            f"{BASE}/current",
            params={"entity_type": "tag_template", "entity_id": batch_id},
        )

    assert current.status_code == 200, current.text
    outcome = current.json()["last_outcome"]
    assert outcome["status"] == "failed", outcome
    assert outcome["error_text"] == "Tag template not found."
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id == a).first() is not None


def test_viewer_without_manage_is_refused_before_anything_is_parked(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        a = _create_template(client)

    _as(_VIEWER_ID)
    with TestClient(app) as client:
        refused = _start(client, [a])

    assert refused.status_code == 403, refused.text
    assert db.query(SlaFormAction).count() == 0
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id == a).first() is not None


def test_cancel_inside_the_window_leaves_every_row_standing(api):
    db, _as, _scope = api

    with TestClient(app) as client:
        a = _create_template(client)
        b = _create_template(client)

        parked = _start(client, [a, b])
        cancelled = client.post(f"{BASE}/{parked.json()['id']}/cancel")

    assert cancelled.status_code == 200, cancelled.text
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id.in_([a, b])).count() == 2
