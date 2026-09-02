"""A parked action commits under the REQUESTER's company scope, not the sweeper's.

The hole this file pins is not specific to any one action. `/pending-actions`
checks a permission SLUG at the click and nothing else - it never loads the
record, so nothing there says which company the named id belongs to. The commit
then happens on a session that authorised nothing: the scheduler sweep runs
`set_company_scope(db, None)` (every company, because a tick has no principal),
and the lazy commit runs inside whoever happened to poll. So a user of company A
could park a delete naming a company-B record and, ten seconds later, the sweep
would carry it out - with the company filter that protects every other read and
write simply not present.

Two shapes are exercised, because the fix is in the engine and has to hold for
both: an ordinary single-record delete (`brand.delete`, standing in for the
thirty-odd registered ones) and the batch action S11 added
(`tag_template.bulk_delete`), whose entity id is a click token rather than a
record at all.

Every commit below is driven through `FormActionService(db).commit_due()` under
`company_scope(db, None)` - the scheduler sweep, exactly as
`_handler_form_action_commit` calls it. `tests/test_tag_template_bulk_delete.py`
covers the lazy-commit-on-read path; this one covers the sweep, which is the
path with no requester anywhere near it.

Postgres only, on the blank scratch schema, seeding its own chain.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.base import company_scope
from app.models.dealer_kit import TagTemplate
from app.models.product import Brand
from app.models.sla import (
    FORM_ACTION_COMMITTED,
    FORM_ACTION_FAILED,
    FORM_ACTION_INELIGIBLE,
    SlaFormAction,
)
from app.services.form_action_service import FormActionService
from tests._pg_fixture import blank_session, unique_code

# `from ... import`, never `import app.services.record_actions`: the latter rebinds the
# name `app` to the PACKAGE and shadows the FastAPI instance imported above.
from app.services import record_actions  # noqa: F401  (registers the record actions)

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ACTOR_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
_ROLE_ID = "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e"

BASE = "/api/v1/pending-actions"

_SLUGS = (
    "dealer_kit.tag_templates.view",
    "dealer_kit.tag_templates.manage",
    "master_data.brands.delete",
)


def _seed_actor(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="zzt_scope_manager",
            name="zzt_scope_manager",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(
        User(
            id=_ACTOR_ID,
            email="zzt-scope-manager@test.com",
            name="Zena Scope",
            status="ACTIVE",
        )
    )
    db.flush()
    db.add(UserRoleAssignment(user_id=_ACTOR_ID, role_id=_ROLE_ID))
    for slug in _SLUGS:
        permission_id = str(uuid.uuid4())
        db.add(UserPermission(id=permission_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=permission_id
            )
        )
    db.commit()


@pytest.fixture
def api():
    """One session, one signed-in manager, and a switchable company scope.

    `_in_company` moves BOTH the request scope (what the route resolves) and the
    session's own, so a row created after it is stamped to that company by the
    `before_insert` auto-stamp - the same way a real second tenant's rows arrive.
    """
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_actor(db)
        other_company = str(uuid.uuid4())
        db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
        db.commit()

        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        principal = {"id": _ACTOR_ID, "email": "zzt-scope-manager@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        yield db, _in_company, other_company

        app.dependency_overrides.clear()


def _create_template(client: TestClient) -> str:
    res = client.post(
        "/api/v1/dealer-kit/tag-templates",
        json={
            "name": unique_code("ZZT Tmpl"),
            "family": "toilet",
            "doc": {"layers": [], "width_mm": 85, "height_mm": 58},
            "print_size": {"width_mm": 85, "height_mm": 58},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _create_brand(db) -> str:
    brand = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code("ZZTB"),
        brand_name="ZZT scope brand",
    )
    db.add(brand)
    db.commit()
    return brand.id


def _park(client: TestClient, action_key: str, entity_type: str, entity_id: str, **payload):
    return client.post(
        BASE,
        json={
            "action_key": action_key,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
        },
    )


def _lapse(db, action_id: str) -> None:
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def _sweep(db) -> dict:
    """The scheduler tick, verbatim: no principal, every company visible."""
    with company_scope(db, None):
        return FormActionService(db).commit_due()


def _row(db, action_id: str) -> SlaFormAction:
    db.expire_all()
    return db.query(SlaFormAction).filter(SlaFormAction.id == action_id).one()


# --------------------------------------------------------------------------- #
# A single-record delete - the shape thirty-odd registered actions share        #
# --------------------------------------------------------------------------- #


def test_a_parked_delete_still_commits_for_the_company_that_asked(api):
    """The stored scope must not break the ordinary case: the requester's own
    record is deleted by the sweep exactly as before."""
    db, _in_company, _other = api

    brand_id = _create_brand(db)
    with TestClient(app) as client:
        parked = _park(client, "brand.delete", "brand", brand_id)
    assert parked.status_code == 202, parked.text

    # Parked WITH the requester's company on it - the whole point, and the thing
    # a legacy row (parked before this key existed) does not have.
    assert _row(db, parked.json()["id"]).payload_json["__company_scope"] == [_SORENTO]

    _lapse(db, parked.json()["id"])
    assert _sweep(db)["committed"] == 1

    assert _row(db, parked.json()["id"]).status == FORM_ACTION_COMMITTED
    db.expire_all()
    assert db.query(Brand).filter(Brand.id == brand_id).first() is None


def test_the_sweep_will_not_delete_another_companys_record(api):
    """The click checked a permission SLUG, never a company. So a company-A user
    naming a company-B id gets an action that finds nothing when it runs - not
    one the all-companies sweep carries out for them."""
    db, _in_company, other = api

    _in_company(other)
    theirs = _create_brand(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        parked = _park(client, "brand.delete", "brand", theirs)
    assert parked.status_code == 202, parked.text

    _lapse(db, parked.json()["id"])
    _sweep(db)

    row = _row(db, parked.json()["id"])
    assert row.status in (FORM_ACTION_INELIGIBLE, FORM_ACTION_FAILED), row.status
    _in_company(other)
    db.expire_all()
    assert db.query(Brand).filter(Brand.id == theirs).first() is not None


def test_an_action_parked_before_the_scope_was_stored_commits_nothing(api):
    """A row from before this key existed is fail-closed, not all-companies.

    UNSET is what a session that never resolved a scope gets everywhere else in
    the codebase, and a delete is the wrong place to start guessing."""
    db, _in_company, _other = api

    brand_id = _create_brand(db)
    with TestClient(app) as client:
        parked = _park(client, "brand.delete", "brand", brand_id)
    action_id = parked.json()["id"]

    # Exactly the shape a row parked by the previous release has.
    row = _row(db, action_id)
    payload = dict(row.payload_json)
    payload.pop("__company_scope")
    row.payload_json = payload
    db.commit()

    _lapse(db, action_id)
    _sweep(db)

    assert _row(db, action_id).status in (FORM_ACTION_INELIGIBLE, FORM_ACTION_FAILED)
    db.expire_all()
    assert db.query(Brand).filter(Brand.id == brand_id).first() is not None


# --------------------------------------------------------------------------- #
# The batch action (S11) - an entity id that is a click token, not a record     #
# --------------------------------------------------------------------------- #


def test_the_sweep_refuses_a_batch_naming_another_companys_template(api):
    """AC-S11-2 through the SWEEP. The service's own company filter is only as
    good as the scope on the session running it, and the sweep's scope is every
    company - so the batch has to be refused by the scope the requester had."""
    db, _in_company, other = api

    with TestClient(app) as client:
        mine = _create_template(client)

    _in_company(other)
    with TestClient(app) as client:
        theirs = _create_template(client)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        parked = _park(
            client,
            "tag_template.bulk_delete",
            "tag_template",
            str(uuid.uuid4()),
            template_ids=[mine, theirs],
        )
    assert parked.status_code == 202, parked.text

    _lapse(db, parked.json()["id"])
    _sweep(db)

    row = _row(db, parked.json()["id"])
    assert row.status in (FORM_ACTION_INELIGIBLE, FORM_ACTION_FAILED), row.status
    assert row.error_text == "Tag template not found."
    # Atomic: the requester's own template is untouched too.
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id == mine).first() is not None
    _in_company(other)
    db.expire_all()
    assert db.query(TagTemplate).filter(TagTemplate.id == theirs).first() is not None


def test_the_sweep_commits_a_batch_of_the_requesters_own_templates(api):
    db, _in_company, _other = api

    with TestClient(app) as client:
        first = _create_template(client)
        second = _create_template(client)
        parked = _park(
            client,
            "tag_template.bulk_delete",
            "tag_template",
            str(uuid.uuid4()),
            template_ids=[first, second],
        )
    assert parked.status_code == 202, parked.text

    _lapse(db, parked.json()["id"])
    assert _sweep(db)["committed"] == 1

    db.expire_all()
    assert (
        db.query(TagTemplate).filter(TagTemplate.id.in_([first, second])).count() == 0
    )


def test_the_handler_never_sees_the_engines_reserved_key(api):
    """The scope travels in the payload, so the payload the handler is handed has
    to be the one the caller sent - nothing else may start reading `__`-prefixed
    keys, or the two would be a contract nobody wrote down."""
    db, _in_company, _other = api
    seen: list[dict] = []

    from app.services.form_action_registry import REGISTRY

    action = REGISTRY["tag_template.bulk_delete"]
    original = action.execute

    def _spy(session, payload):
        seen.append(dict(payload))
        return original(session, payload)

    object.__setattr__(action, "execute", _spy)
    try:
        with TestClient(app) as client:
            template_id = _create_template(client)
            parked = _park(
                client,
                "tag_template.bulk_delete",
                "tag_template",
                str(uuid.uuid4()),
                template_ids=[template_id],
            )
        _lapse(db, parked.json()["id"])
        _sweep(db)
    finally:
        object.__setattr__(action, "execute", original)

    assert seen, "the handler never ran"
    assert "__company_scope" not in seen[0]
    assert seen[0]["template_ids"] == [template_id]
