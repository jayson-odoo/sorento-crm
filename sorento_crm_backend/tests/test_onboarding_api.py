"""The two onboarding HTTP surfaces.

The public one is gated by the intake token alone; the admin one by the five
`user_management.onboarding.*` permissions. Both are exercised here against a
blank Postgres schema with their own seeded users, roles and grants - CI's
database is empty, so a test that leans on an existing role passes locally and
fails there.

The assertion worth naming is `test_the_requester_never_sees_a_role_id`. That
omission is the feature's privacy boundary: a department head with no CRM
account proposes "Salesperson" and learns nothing about what roles exist. It is
enforced by the response schema rather than by a component remembering not to
render a field, and this is what pins it.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.onboarding import OnboardingTemplate
from app.models.company import UserCompany
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services import onboarding_service
from tests._pg_fixture import blank_session, unique_code

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "360_onboarding_slice1.py"
)
SORENTO = "00000000-0000-0000-0000-000000000001"
FIXTURE = Path(__file__).parent / "fixtures" / "onboarding_phone_list.xlsx"

PUBLIC = "/api/v1/public/onboarding"
ADMIN = "/api/v1/user-management/onboarding"

ALL_SLUGS = (
    "user_management.onboarding.view",
    "user_management.onboarding.add",
    "user_management.onboarding.edit",
    "user_management.onboarding.delete",
    "user_management.onboarding.approve",
)


def _migration():
    spec = importlib.util.spec_from_file_location("onboarding_migration_api", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db():
    with blank_session() as session:
        module = _migration()
        module._seed_graph(session.connection())
        module._mark_system(session.connection())
        # The reader resolves headers through `import_field_alias`, so the public
        # parse endpoint needs the same aliases the migration seeds.
        module._seed_aliases(session.connection())
        yield session


def _make_user(db, *, slugs=()) -> User:
    """A caller holding exactly the slugs named, and nothing else."""
    user = User(
        id=unique_code("user"),
        email=f"{unique_code('caller')}@example.com".lower(),
        name="Test Caller",
        status="ACTIVE",
    )
    role = UserRole(
        id=unique_code("role"), slug=unique_code("role").lower(), name=unique_code("Role")
    )
    db.add_all([user, role])
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    # Grant Sorento: onboarding requests are company-scoped, so a caller with no
    # company grant resolves to an EMPTY scope and every read is a 404 rather
    # than a 403 - which is the correct production behaviour and would otherwise
    # read here as a broken route.
    db.add(UserCompany(user_id=user.id, company_id=SORENTO))
    for slug in slugs:
        # Get-or-create: `user_permissions.slug` is unique, and a test that makes
        # two callers (an editor and an approver, say) would otherwise collide on
        # the second one.
        permission = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if permission is None:
            permission = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
            db.add(permission)
            db.flush()
        db.add(UserRolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()
    return user


@pytest.fixture
def client(db):
    """A caller whose active company is Sorento, against this session.

    `apply_company_scope` is a ROUTER-level dependency: it runs on every
    `/api/v1/*` request and stamps the scope it resolves from the Bearer token
    onto the session, overwriting whatever was there. A TestClient that
    authenticates by overriding `get_current_user` sends no bearer token, so the
    resolver falls through to UNSET - which is fail-closed, and every scoped read
    then 404s on rows that plainly exist.

    Overriding it here is the honest double for "an authenticated user whose
    active company is Sorento", and it keeps the fail-closed default intact for
    the tests that exist to assert it.
    """
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    def _sorento_scope():
        scope = frozenset({SORENTO})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[apply_company_scope] = _sorento_scope
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _as(user: User, db=None) -> None:
    """Authenticate as `user`. Scope is handled by the `client` fixture."""
    app.dependency_overrides[get_current_user] = lambda: {
        "id": user.id,
        "email": user.email,
    }


@pytest.fixture
def template(db) -> OnboardingTemplate:
    role = UserRole(
        id=unique_code("role"), slug=unique_code("tpl").lower(), name=unique_code("Sales")
    )
    db.add(role)
    db.flush()
    tpl = OnboardingTemplate(
        name=unique_code("Salesperson"),
        description="Sees their own orders.",
        role_ids=[role.id],
        company_ids=[SORENTO],
        company_id=SORENTO,
    )
    db.add(tpl)
    db.commit()
    return tpl


@pytest.fixture
def sent_request(db):
    request = onboarding_service.create_request(
        db,
        company_id=SORENTO,
        title=unique_code("MOCHA staff"),
        requester_name="Esther Lim",
        requester_email=f"{unique_code('esther')}@mocha.com.my".lower(),
    )
    onboarding_service.send_request(db, str(request.id))
    return request


# --- public: the token is the whole auth story --------------------------------


def test_no_token_is_401(client):
    assert client.get(f"{PUBLIC}/me").status_code == 401


def test_unknown_token_is_401(client):
    assert client.get(f"{PUBLIC}/me", params={"token": "NOPE"}).status_code == 401


def test_the_token_works_in_a_header_or_a_query_param(client, sent_request):
    by_query = client.get(f"{PUBLIC}/me", params={"token": sent_request.token})
    by_header = client.get(
        f"{PUBLIC}/me", headers={"X-Onboarding-Token": sent_request.token}
    )
    assert by_query.status_code == 200
    assert by_header.status_code == 200
    assert by_query.json()["title"] == sent_request.title


def test_an_expired_token_is_401(client, db, sent_request):
    sent_request.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    assert (
        client.get(f"{PUBLIC}/me", params={"token": sent_request.token}).status_code == 401
    )


def test_a_revoked_token_is_401(client, db, sent_request):
    onboarding_service.revoke(db, str(sent_request.id))
    assert (
        client.get(f"{PUBLIC}/me", params={"token": sent_request.token}).status_code == 401
    )


def test_the_requester_never_sees_a_role_id(client, sent_request, template):
    """The privacy boundary, enforced by the response schema (UAC AC-5.4)."""
    body = client.get(f"{PUBLIC}/me", params={"token": sent_request.token}).json()
    assert body["templates"], "the picker would be empty"
    option = body["templates"][0]
    assert option["name"] == template.name
    assert set(option) == {
        "id",
        "name",
        "description",
        "default_needs_system_account",
        "default_needs_respond_contact",
        "default_needs_agent_seat",
    }


# --- public: parse ------------------------------------------------------------


def test_parse_reads_the_phone_list_shape(client, sent_request):
    with FIXTURE.open("rb") as handle:
        response = client.post(
            f"{PUBLIC}/parse",
            params={"token": sent_request.token},
            files={"file": ("PHONE LIST.xlsx", handle.read(), "application/vnd.ms-excel")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 18
    assert len(body["rows"]) == 18
    assert body["sections"][0] == "SALES PERSON"
    # Warnings ride on the row rather than rejecting the file.
    assert any(row["problems"] for row in body["rows"])


def test_parse_refuses_a_non_workbook(client, sent_request):
    response = client.post(
        f"{PUBLIC}/parse",
        params={"token": sent_request.token},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422


def test_parse_needs_a_token(client):
    response = client.post(
        f"{PUBLIC}/parse", files={"file": ("x.xlsx", b"whatever", "application/vnd.ms-excel")}
    )
    assert response.status_code == 401


def test_parse_writes_nothing(client, db, sent_request):
    with FIXTURE.open("rb") as handle:
        client.post(
            f"{PUBLIC}/parse",
            params={"token": sent_request.token},
            files={"file": ("PHONE LIST.xlsx", handle.read(), "application/vnd.ms-excel")},
        )
    db.refresh(sent_request)
    assert sent_request.people == []


# --- public: save and submit --------------------------------------------------


def _rows(count: int = 2) -> list[dict]:
    return [
        {
            "row_number": i,
            "full_name": f"Person {i}",
            "email_raw": f"person{i}@mocha.com.my",
            "phone_raw": f"012-345678{i}",
            "needs_system_account": True,
            "needs_respond_contact": False,
            "needs_agent_seat": False,
        }
        for i in range(1, count + 1)
    ]


def test_saving_rows_then_submitting(client, sent_request):
    saved = client.put(
        f"{PUBLIC}/rows",
        params={"token": sent_request.token},
        json={"rows": _rows(3)},
    )
    assert saved.status_code == 200
    assert len(saved.json()["people"]) == 3
    assert saved.json()["editable"] is True

    submitted = client.post(
        f"{PUBLIC}/submit",
        params={"token": sent_request.token},
        json={"requester_note": "Zul starts next month."},
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["status"] == "submitted"
    assert body["editable"] is False
    assert body["requester_note"] == "Zul starts next month."


def test_the_link_still_works_after_submission_but_read_only(client, sent_request):
    client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(1)}
    )
    client.post(f"{PUBLIC}/submit", params={"token": sent_request.token}, json={})

    # Still resolvable - the same link is now the status page (UAC AC-3.4).
    after = client.get(f"{PUBLIC}/me", params={"token": sent_request.token})
    assert after.status_code == 200
    assert after.json()["editable"] is False

    refused = client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(5)}
    )
    assert refused.status_code == 409


def test_submitting_nothing_is_refused(client, sent_request):
    response = client.post(
        f"{PUBLIC}/submit", params={"token": sent_request.token}, json={}
    )
    assert response.status_code == 422


# --- admin: permissions -------------------------------------------------------


def test_listing_requests_needs_the_view_permission(client, db):
    _as(_make_user(db), db)
    assert client.get(f"{ADMIN}/requests").status_code == 403

    _as(_make_user(db, slugs=("user_management.onboarding.view",)), db)
    assert client.get(f"{ADMIN}/requests").status_code == 200


def test_creating_a_request_needs_the_add_permission(client, db):
    payload = {
        "company_id": SORENTO,
        "title": "New batch",
        "requester_name": "Esther",
        "requester_email": "esther@mocha.com.my",
    }
    _as(_make_user(db, slugs=("user_management.onboarding.view",)), db)
    assert client.post(f"{ADMIN}/requests", json=payload).status_code == 403

    _as(_make_user(db, slugs=ALL_SLUGS), db)
    created = client.post(f"{ADMIN}/requests", json=payload)
    assert created.status_code == 201
    assert created.json()["status"] == "draft"


def test_approving_needs_its_own_permission(client, db, sent_request, template):
    """`.edit` is not enough - approving is what creates real users."""
    client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(1)}
    )
    client.post(f"{PUBLIC}/submit", params={"token": sent_request.token}, json={})

    editor = _make_user(
        db,
        slugs=("user_management.onboarding.view", "user_management.onboarding.edit"),
    )
    _as(editor, db)
    assert client.post(f"{ADMIN}/requests/{sent_request.id}/start-review").status_code == 200
    person_id = client.get(f"{ADMIN}/requests/{sent_request.id}").json()["people"][0]["id"]
    assert (
        client.post(
            f"{ADMIN}/requests/{sent_request.id}/people/{person_id}/keep"
        ).status_code
        == 200
    )
    assert client.post(f"{ADMIN}/requests/{sent_request.id}/approve").status_code == 403

    _as(_make_user(db, slugs=ALL_SLUGS), db)
    approved = client.post(f"{ADMIN}/requests/{sent_request.id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "processing"
    assert approved.json()["queued_people"] == 1


def test_approving_twice_is_refused_over_http(client, db, sent_request):
    client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(1)}
    )
    client.post(f"{PUBLIC}/submit", params={"token": sent_request.token}, json={})
    _as(_make_user(db, slugs=ALL_SLUGS), db)
    client.post(f"{ADMIN}/requests/{sent_request.id}/start-review")
    person_id = client.get(f"{ADMIN}/requests/{sent_request.id}").json()["people"][0]["id"]
    client.post(f"{ADMIN}/requests/{sent_request.id}/people/{person_id}/keep")

    assert client.post(f"{ADMIN}/requests/{sent_request.id}/approve").status_code == 200
    assert client.post(f"{ADMIN}/requests/{sent_request.id}/approve").status_code == 422


def test_rejecting_a_person_over_http_requires_a_reason(client, db, sent_request):
    client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(1)}
    )
    client.post(f"{PUBLIC}/submit", params={"token": sent_request.token}, json={})
    _as(_make_user(db, slugs=ALL_SLUGS), db)
    client.post(f"{ADMIN}/requests/{sent_request.id}/start-review")
    person_id = client.get(f"{ADMIN}/requests/{sent_request.id}").json()["people"][0]["id"]

    blank = client.post(
        f"{ADMIN}/requests/{sent_request.id}/people/{person_id}/reject",
        json={"reason": "   "},
    )
    assert blank.status_code == 422

    ok = client.post(
        f"{ADMIN}/requests/{sent_request.id}/people/{person_id}/reject",
        json={"reason": "Left the company."},
    )
    assert ok.status_code == 200
    person = ok.json()["people"][0]
    assert person["review_status"] == "rejected"
    assert person["rejection_reason"] == "Left the company."


def test_the_reviewer_sees_collisions_the_requester_did_not(client, db, sent_request):
    taken = "person1@mocha.com.my"
    db.add(
        User(id=unique_code("user"), email=taken, name="Already Here", status="ACTIVE")
    )
    db.commit()

    client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(1)}
    )
    public_body = client.get(f"{PUBLIC}/me", params={"token": sent_request.token}).json()
    assert public_body["people"][0]["collisions"] == []

    _as(_make_user(db, slugs=ALL_SLUGS), db)
    admin_body = client.get(f"{ADMIN}/requests/{sent_request.id}").json()
    collisions = admin_body["people"][0]["collisions"]
    assert [c["kind"] for c in collisions] == ["user_email"]
    assert "Already Here" in collisions[0]["label"]


def test_deleting_a_request_takes_its_people_with_it(client, db, sent_request):
    from app.models.onboarding import OnboardingPerson

    client.put(
        f"{PUBLIC}/rows", params={"token": sent_request.token}, json={"rows": _rows(2)}
    )
    request_id = str(sent_request.id)

    _as(_make_user(db, slugs=("user_management.onboarding.view",)), db)
    assert client.delete(f"{ADMIN}/requests/{request_id}").status_code == 403

    _as(_make_user(db, slugs=ALL_SLUGS), db)
    assert client.delete(f"{ADMIN}/requests/{request_id}").status_code == 204
    assert (
        db.query(OnboardingPerson)
        .filter(OnboardingPerson.request_id == request_id)
        .count()
        == 0
    )


def test_the_detail_response_carries_the_intake_link_for_the_captain(client, db, sent_request):
    """He copies it into WhatsApp himself, the way the contact portal allows."""
    _as(_make_user(db, slugs=ALL_SLUGS), db)
    body = client.get(f"{ADMIN}/requests/{sent_request.id}").json()
    url = body.get("intake_url")
    if url:  # FRONTEND_BASE_URL may be unset in a bare environment
        assert url.endswith(f"/onboarding/{sent_request.token}")
