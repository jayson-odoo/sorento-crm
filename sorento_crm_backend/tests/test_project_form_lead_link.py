"""Phase 2 RED tests for lane #1339 (project form: lead link, admin_ref, owner pick).

Tests the CONTRACT documented in `PLAN-project-form-28sep.md` (D5-D9) and
`project-form-28sep-acceptance-criteria.md` (AC-PF017, AC-PF041..043, AC-PF051..059,
AC-PF070). Nothing in this file relies on any FE code; every assertion goes through
the FastAPI TestClient against the real (Postgres, blank-schema) service layer.

None of the following exist yet in `app/schemas/projects.py` /
`app/services/project_lead_service.py` at RED time:
  - `lead_id` on `ProjectRegisterRequest` and `ProjectUpdateRequest`
  - `admin_ref` on `ProjectRegisterRequest`
  - a `link_lead` (or equivalent) service function wired into register/update

Pydantic v2 ignores unknown request fields by default, so a payload carrying
`lead_id` / `admin_ref` today is silently accepted and the field is simply dropped --
these tests are expected to fail on the ASSERTION (wrong value / wrong status code),
not on collection or on an unrelated fixture error. A handful of tests pin behaviour
that already exists (owner pick, edit permission, qualify's own multi-project
exemption, the existing field round trip) and are expected to be GREEN already; they
are kept so a later regression on this same file is caught.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.product import Brand
from app.models.projects import ProjectLead, ProjectParty
from app.models.user import User
from app.services import project_lead_service
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-form-lead-link"
PROJECTS_BASE = "/api/v1/project-sales/projects"
LEADS_BASE = "/api/v1/project-sales/leads"

FULL_PERMS = [
    "projects.projects.view",
    "projects.projects.create",
    "projects.projects.edit",
    "projects.projects.delete",
    "projects.projects.manage",
]
NO_MANAGE_PERMS = [
    "projects.projects.view",
    "projects.projects.create",
    "projects.projects.edit",
    "projects.projects.delete",
]


def _uid() -> str:
    return str(uuid.uuid4())


def _title(stem: str) -> str:
    """A title unique per call: the clash matcher blocks near-duplicate titles under
    the same developer, and every test here registers under no developer at all --
    so two tests sharing a stem would still collide on the exact-title fast path.

    The full uuid, not 8 hex: with 8, two `_title("Project")` calls cross the 0.70 block
    bar about 7 times in 20,000 pairs (measured with pg_trgm `similarity()`), and the
    second registration is then refused as `project_already_registered` before the lead
    check runs. With 32 the highest score measured was 0.36."""
    return f"{MARKER} {stem} {uuid.uuid4().hex}"


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _party(db, company_id: str, party_type: str, name: str) -> ProjectParty:
    party = ProjectParty(company_id=company_id, party_type=party_type, name=name)
    db.add(party)
    db.flush()
    return party


def _brand(db, company_id: str, name: str) -> Brand:
    brand = Brand(
        company_id=company_id,
        brand_code=f"ZZT-{uuid.uuid4().hex[:8]}",
        brand_name=name,
    )
    db.add(brand)
    db.flush()
    return brand


def _client(db, user_id: str, perms):
    """A TestClient acting as `user_id`, holding exactly `perms`.

    `check_user_has_permission` always returns True (the route-level gate is not what
    is under test here); the rules under test live in the SERVICE layer, reading
    `get_user_permission_slugs`.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "superadmin"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    # The router-level resolver re-stamps the scope from the REQUEST, which has no
    # active company here, and would overwrite the fixture's pin with UNSET.
    app.dependency_overrides[apply_company_scope] = lambda: None

    original_check = UserPermissionService.check_user_has_permission
    original_slugs = UserPermissionService.get_user_permission_slugs
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(perms)

    client = TestClient(app)
    return client, (original_check, original_slugs)


def _restore(originals) -> None:
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    from app.main import app

    app.dependency_overrides.clear()


@pytest.fixture()
def api():
    """One session, company scope pinned, one full-permission user by default.

    A test that needs a second actor calls `_client(db, other_user_id, perms)`
    directly and discards the returned originals -- only the FIRST client's
    originals (captured here, before any monkeypatch has happened) are used to
    restore the real `UserPermissionService` methods on teardown.
    """
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Admin")
        from ._sample_request_seed import make_customer

        _REGISTER_CUSTOMER["id"] = make_customer(db, company_id).id
        db.commit()
        client, originals = _client(db, user_id, FULL_PERMS)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, user_id
        finally:
            _restore(originals)


#: A register call needs a customer (PROJECT-REGISTER-V2 A5); the fixture seeds one.
_REGISTER_CUSTOMER: dict = {}


def _create_lead(client, **overrides):
    # LEAD-GOVERNS-REGISTER B1: a lead carries a customer, so every test lead gets the
    # fixture's customer unless a test names its own.
    payload = {"title": _title("Lead"), "customer_id": _REGISTER_CUSTOMER["id"]}
    payload.update(overrides)
    return client.post(LEADS_BASE, json=payload)


def _register(client, **overrides):
    """Register a project (no lead: registration never links one, AC-L2/L4)."""
    payload = {"title": _title("Project"), "customer_id": _REGISTER_CUSTOMER["id"]}
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}  # None = leave the key out
    return client.post(f"{PROJECTS_BASE}/", json=payload)


def _register_without_lead(client, **overrides):
    return _register(client, **overrides)


# --------------------------------------------------------- register / update basics


def test_register_with_a_lead_id_ignores_it_and_still_stamps_admin_ref(api):
    """AC-L4 (flipped from AC-PF051): admin_ref is carried; the lead is neither linked nor
    qualified."""
    client, db, _company_id, _user_id = api
    lead = _create_lead(client).json()

    response = _register(client, lead_id=lead["id"], admin_ref="PS26-0143")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["lead_id"] is None
    assert body["admin_ref"] == "PS26-0143"

    refreshed_lead = client.get(f"{LEADS_BASE}/{lead['id']}").json()
    assert refreshed_lead["outcome"] == "open"
    assert refreshed_lead["qualified_at"] is None


def test_update_with_a_lead_id_ignores_it_ac_l5(api):
    client, _db, _company_id, _user_id = api
    project = _register(client).json()
    lead = _create_lead(client).json()

    response = client.put(f"{PROJECTS_BASE}/{project['id']}", json={"lead_id": lead["id"]})

    assert response.status_code == 200, response.text
    assert response.json()["lead_id"] is None
    refreshed_lead = client.get(f"{LEADS_BASE}/{lead['id']}").json()
    assert refreshed_lead["outcome"] == "open"
    assert refreshed_lead["qualified_at"] is None


# ------------------------------------------------------------------------ refusals


# -------------------------------------------------------------- unlink / swap / noop


# ------------------------------------------------------------------------- qualify


def test_qualify_is_unchanged_and_still_allows_two_projects_from_one_lead(api):
    """AC-PF059 / plan Q2: the form's already-linked refusal must NOT reach Qualify.
    Pinning: this should already pass, since qualify_lead never applies it."""
    client, _db, _company_id, _user_id = api
    lead = _create_lead(client).json()

    first = client.post(
        f"{LEADS_BASE}/{lead['id']}/qualify", json={"title": _title("Phase 1")}
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{LEADS_BASE}/{lead['id']}/qualify", json={"title": _title("Phase 2")}
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["lead_id"] == lead["id"] == first.json()["lead_id"]


# --------------------------------------------------------------------- owner pick


def test_manage_holder_can_register_a_project_for_another_salesperson(api):
    """AC-PF041. Pinning: unchanged rule."""
    client, db, _company_id, _admin_id = api
    salesperson_id = _user(db, f"{MARKER} Salesperson")

    response = _register(client, owner_user_id=salesperson_id)

    assert response.status_code == 201, response.text
    assert response.json()["owner_user_id"] == salesperson_id


def test_non_manage_user_cannot_register_a_project_for_someone_else(api):
    """AC-PF042. Pinning: unchanged rule."""
    client, db, _company_id, _admin_id = api
    other_id = _user(db, f"{MARKER} Other")
    caller_id = _user(db, f"{MARKER} Caller")
    caller_client, _ = _client(db, caller_id, NO_MANAGE_PERMS)

    response = _register(caller_client, owner_user_id=other_id)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "project_owner_assign_forbidden"


def test_owner_reassignment_on_update_needs_manage(api):
    """AC-PF043. Pinning: unchanged rule."""
    client, db, _company_id, admin_id = api
    owner_id = _user(db, f"{MARKER} Owner")
    other_id = _user(db, f"{MARKER} Other")
    # Committed now, before any route call that could 403 and roll the session back to
    # its last commit -- a flushed-but-uncommitted row would be undone by that rollback
    # and then be missing (FK violation) when the manage client references it below.
    db.commit()
    owner_client, _ = _client(db, owner_id, NO_MANAGE_PERMS)
    project = _register(owner_client).json()

    refused = owner_client.put(
        f"{PROJECTS_BASE}/{project['id']}", json={"owner_user_id": other_id}
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "project_owner_reassign_forbidden"

    manage_client, _ = _client(db, admin_id, FULL_PERMS)
    allowed = manage_client.put(
        f"{PROJECTS_BASE}/{project['id']}", json={"owner_user_id": other_id}
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["owner_user_id"] == other_id


# ------------------------------------------------------------------ edit permission


def test_edit_permission_on_update_is_unchanged(api):
    """AC-PF070. Pinning: unchanged rule. A non-owner, non-manage third party is
    refused; the owner, even without manage, may still save."""
    client, db, _company_id, admin_id = api
    owner_id = _user(db, f"{MARKER} Owner")
    manage_client, _ = _client(db, admin_id, FULL_PERMS)
    project = _register(manage_client, owner_user_id=owner_id).json()

    third_id = _user(db, f"{MARKER} ThirdParty")
    third_client, _ = _client(db, third_id, NO_MANAGE_PERMS)
    refused = third_client.put(
        f"{PROJECTS_BASE}/{project['id']}", json={"location": "Shah Alam"}
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "project_not_editable"

    owner_client, _ = _client(db, owner_id, NO_MANAGE_PERMS)
    allowed = owner_client.put(
        f"{PROJECTS_BASE}/{project['id']}", json={"location": "Shah Alam"}
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["location"] == "Shah Alam"


# ---------------------------------------------------------------------- full round trip


def test_full_field_round_trip_on_update(api):
    """AC-PF013, AC-PF014, AC-PF017, AC-PF020, AC-PF021, AC-PF022, AC-PF023. Pinning
    for every field except `admin_ref`, which already exists on `ProjectUpdateRequest`
    too -- so this whole test should already be GREEN."""
    client, db, company_id, _user_id = api
    project = _register(client).json()
    brand = _brand(db, company_id, f"{MARKER} Brand")
    architect = _party(db, company_id, "architect", f"{MARKER} Architect")
    main_contractor = _party(db, company_id, "main_contractor", f"{MARKER} MC")

    payload = {
        "brand_ids": [brand.id],
        "location": "Petaling Jaya",
        "address": "Lot 1, Jalan Test",
        "expected_delivery_from": "2027-01-01",
        "expected_delivery_to": "2027-06-30",
        "admin_ref": "PS26-9999",
        "architect_party_id": architect.id,
        "main_contractor_party_id": main_contractor.id,
    }

    response = client.put(f"{PROJECTS_BASE}/{project['id']}", json=payload)
    assert response.status_code == 200, response.text

    fetched = client.get(f"{PROJECTS_BASE}/{project['id']}").json()
    assert "brand_ids" not in fetched  # brands are removed from the project API
    assert fetched["location"] == "Petaling Jaya"
    assert fetched["address"] == "Lot 1, Jalan Test"
    assert fetched["expected_delivery_from"] == "2027-01-01"
    assert fetched["expected_delivery_to"] == "2027-06-30"
    assert fetched["admin_ref"] == "PS26-9999"
    assert fetched["architect_party_id"] == architect.id
    assert fetched["main_contractor_party_id"] == main_contractor.id


# ------------------------------------------------ review round (PR #1345, round 1)


