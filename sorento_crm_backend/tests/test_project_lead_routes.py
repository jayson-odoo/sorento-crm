"""S2c lead ROUTES, not the service (UAC Group O).

These exist because of a real bug the service tests could not catch: the qualify route
called ``serialize_projects(user_id=...)`` while the serializer's argument is
``actor_user_id``, so the endpoint 500'd on a path every service test passed. A route
is its own seam -- the wiring between HTTP and the service is code too, and it needs a
test that actually goes through FastAPI.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.order import Customer
from app.models.projects import ProjectParty
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-lead-route"
BASE = "/api/v1/project-sales/leads"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _customer(db, company_id: str, name: str) -> Customer:
    customer = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{name[:6]}",
        customer_name=name,
    )
    db.add(customer)
    db.flush()
    return customer


def _client(db, user_id: str):
    """Every permission granted: these tests are about wiring, not about RBAC, which
    has its own tests."""
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
    # active company here, and would overwrite the fixture's pin with UNSET. Overriding
    # it is what a real JWT carrying `active_company_id` does in production.
    app.dependency_overrides[apply_company_scope] = lambda: None

    original_check = UserPermissionService.check_user_has_permission
    original_slugs = UserPermissionService.get_user_permission_slugs
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.projects.view",
        "projects.projects.create",
        "projects.projects.edit",
        "projects.projects.delete",
        "projects.projects.manage",
    ]

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
    """One session shared by the test and the routes, with the company scope pinned.

    The scope normally comes from the request middleware, which the TestClient
    dependency override bypasses -- and ``acting_company_id`` fails closed on an
    unresolved scope, exactly as it should. Pinning it here is what the middleware
    would have done.
    """
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        user_id = _user(db, f"{MARKER} Ali")
        client, originals = _client(db, user_id)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, user_id
        finally:
            _restore(originals)


def test_recording_and_reading_a_lead_round_trips_through_http(api):
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")

    created = client.post(
        BASE,
        json={
            "title": "Tower behind the showroom",
            "customer_id": customer.id,
            "source": "site_visit",
            "estimated_value": "750000.00",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["lead_code"].startswith("LEAD-")
    assert body["customer_name"] == f"{MARKER} Informant"
    assert body["can_edit"] is True

    listed = client.get(BASE, params={"outcome": ["open"]})
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["data"]] == [body["id"]]

    fetched = client.get(f"{BASE}/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Tower behind the showroom"


def test_the_wizard_can_create_its_customer_in_the_same_request(api):
    client, _db, _company_id, _user_id = api

    response = client.post(
        BASE,
        json={
            "title": "Heard about it from an architect",
            "new_customer": {"customer_name": f"{MARKER} Veritas Architects"},
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["customer_name"] == f"{MARKER} Veritas Architects"


def test_a_lead_with_neither_customer_nor_new_customer_is_accepted(api):
    """AC-A1: the buyer is optional now, so the route must not invent one.

    This asserted a 422 under AC-O1. The premise changed: whoever mentioned the job is
    the informant, and the buyer is whoever eventually places the order, who is usually
    unknown at this point.
    """
    client, _db, _company_id, _user_id = api

    response = client.post(BASE, json={"title": "Somebody heard something"})

    assert response.status_code == 201, response.text
    assert response.json()["customer_id"] is None


def test_qualifying_returns_the_serialised_project(api):
    """The regression this file was created for: the route serialised the project with
    the wrong keyword and 500'd, while every service test passed."""
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")

    lead = client.post(
        BASE, json={"title": "Setia Alam Phase 9", "customer_id": customer.id}
    ).json()

    response = client.post(f"{BASE}/{lead['id']}/qualify", json={})

    assert response.status_code == 201, response.text
    project = response.json()
    assert project["project_code"].startswith("PRJ-")
    assert project["lead_id"] == lead["id"]
    assert project["lead_code"] == lead["lead_code"]
    # Serialised as a project, so the human identifiers are resolved, not raw ids.
    assert "owner_name" in project


def test_qualifying_onto_an_existing_registration_returns_409_and_leaves_the_lead_open(api):
    client, db, company_id, user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")
    developer = ProjectParty(
        id=_uid(), company_id=company_id, party_type="developer", name=f"{MARKER} Setia"
    )
    db.add(developer)
    db.flush()

    from app.services.project_service import register_project

    register_project(
        db,
        company_id=company_id,
        actor_user_id=user_id,
        developer_party_id=developer.id,
        title="Setia Alam Phase 9",
    )
    db.commit()

    lead = client.post(
        BASE,
        json={
            "title": "Setia Alam Ph 9",
            "customer_id": customer.id,
            "developer_party_id": developer.id,
        },
    ).json()

    blocked = client.post(f"{BASE}/{lead['id']}/qualify", json={})
    assert blocked.status_code == 409, blocked.text

    still_open = client.get(f"{BASE}/{lead['id']}").json()
    assert still_open["outcome"] == "open"


def test_the_qualify_preview_describes_the_clash_the_same_way_registration_does(api):
    """One shared serializer, so the preview and the refusal cannot disagree."""
    client, db, company_id, user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")
    developer = ProjectParty(
        id=_uid(), company_id=company_id, party_type="developer", name=f"{MARKER} Setia"
    )
    db.add(developer)
    db.flush()

    from app.services.project_service import register_project

    register_project(
        db,
        company_id=company_id,
        actor_user_id=user_id,
        developer_party_id=developer.id,
        title="Setia Alam Phase 9",
    )
    db.commit()

    lead = client.post(
        BASE,
        json={
            "title": "Setia Alam Phase 9",
            "customer_id": customer.id,
            "developer_party_id": developer.id,
        },
    ).json()

    preview = client.get(f"{BASE}/{lead['id']}/qualify-preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["would_block"] is True
    candidate = body["candidates"][0]
    # The context that makes a block judgeable rather than arbitrary (AC-C6a).
    assert candidate["project_code"].startswith("PRJ-")
    assert candidate["owner_name"]
    assert candidate["blocks"] is True


def test_disqualify_refuses_an_unlisted_reason_and_accepts_a_configured_one(api):
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")
    lead = client.post(
        BASE, json={"title": "Dead rumour", "customer_id": customer.id}
    ).json()

    reasons = client.get(f"{BASE}/disqualify-reasons")
    assert reasons.status_code == 200, reasons.text
    values = {row["value"] for row in reasons.json()}
    assert "budget" in values

    invented = client.post(
        f"{BASE}/{lead['id']}/disqualify", json={"reason": "couldnt be bothered"}
    )
    assert invented.status_code == 422, invented.text

    accepted = client.post(f"{BASE}/{lead['id']}/disqualify", json={"reason": "budget"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["outcome"] == "disqualified"

    reopened = client.post(f"{BASE}/{lead['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["outcome"] == "open"
    assert reopened.json()["disqualified_reason"] is None


def test_the_metrics_endpoint_reports_conversion_and_reason_counts(api):
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")

    won = client.post(BASE, json={"title": "Converted", "customer_id": customer.id}).json()
    client.post(f"{BASE}/{won['id']}/qualify", json={})
    lost = client.post(BASE, json={"title": "Dead", "customer_id": customer.id}).json()
    client.post(f"{BASE}/{lost['id']}/disqualify", json={"reason": "budget"})

    metrics = client.get(f"{BASE}/metrics")
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["qualified"] == 1
    assert body["disqualified"] == 1
    assert body["conversion_rate"] == 0.5
    assert body["disqualified_reasons"] == [
        {"value": "budget", "label": "Budget too low", "count": 1}
    ]


def test_the_customer_portfolio_endpoint_is_not_captured_as_a_lead_id(api):
    """`/leads/by-customer/...` must beat `/leads/{lead_id}` in declaration order, or
    "by-customer" is parsed as a uuid and 404s."""
    client, db, company_id, _user_id = api
    customer = _customer(db, company_id, f"{MARKER} Informant")
    lead = client.post(
        BASE, json={"title": "A sighting", "customer_id": customer.id}
    ).json()

    response = client.get(f"{BASE}/by-customer/{customer.id}/portfolio")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["leads"]] == [lead["id"]]
    assert body["projects"] == []


def test_the_two_terminal_rungs_are_refused_by_the_status_endpoint(api):
    client, db, company_id, _user_id = api
    from app.models.status import Status

    customer = _customer(db, company_id, f"{MARKER} Informant")
    lead = client.post(
        BASE, json={"title": "A sighting", "customer_id": customer.id}
    ).json()

    for key in ("qualified", "disqualified"):
        target = (
            db.query(Status)
            .filter(
                Status.entity_type == "project_lead",
                Status.scope_id.is_(None),
                Status.key == key,
            )
            .first()
        )
        refused = client.post(
            f"{BASE}/{lead['id']}/status", json={"to_status_id": target.id}
        )
        assert refused.status_code == 422, refused.text

    contacted = (
        db.query(Status)
        .filter(
            Status.entity_type == "project_lead",
            Status.scope_id.is_(None),
            Status.key == "contacted",
        )
        .first()
    )
    moved = client.post(
        f"{BASE}/{lead['id']}/status", json={"to_status_id": contacted.id}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status_key"] == "contacted"
