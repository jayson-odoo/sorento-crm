"""The project's customer (owner hand-test, 13 Oct, points 18-19; PROJECT-REGISTER-V2 A5).

The customer is the one picked on the register form (`sales_profile.customer_id`); a project
registered before that field existed has none picked and reads its lead's buyer instead
(`project_service._effective_customer_id`). The project payload names that customer, with the
phone and the main contact the quotation header defaults to, so neither the Overview nor the
quotation form has to make a second trip. A project with neither says so with nulls.
"""
from __future__ import annotations

import uuid

from app.models.order import CustomerContact
from app.models.projects import ProjectSalesProfile

from .test_project_form_lead_link import (  # noqa: F401  (api is a fixture)
    _REGISTER_CUSTOMER,
    FULL_PERMS,
    PROJECTS_BASE,
    _client,
    _create_lead,
    _register,
    api,
)

CUSTOMERS_VIEW = "order_management.customers.view"


def _as(db, user_id, perms):
    """Re-point the TestClient at the same user with a different permission set."""
    client, _originals = _client(db, user_id, perms)
    return client


def _registered_before_v2(db, project_id):
    """A project saved before PROJECT-REGISTER-V2: no customer picked on the form."""
    db.query(ProjectSalesProfile).filter(ProjectSalesProfile.project_id == project_id).update(
        {ProjectSalesProfile.customer_id: None}
    )
    db.flush()


def test_a_project_names_its_customer_with_phone_and_main_contact(api):
    client, db, company_id, _user_id = api
    lead = _create_lead(
        client,
        new_customer={
            "customer_name": f"zzt Gamuda Builders {uuid.uuid4().hex[:8]}",
            "phone_number": "012-345 6789",
        },
    ).json()
    assert lead["customer_id"], lead
    db.add(
        CustomerContact(
            company_id=company_id,
            customer_id=lead["customer_id"],
            full_name="Lim Wei Ming",
            contact_role="main",
        )
    )
    db.flush()

    project = _register(client, lead_id=lead["id"], customer_id=lead["customer_id"]).json()
    reader = _as(db, _user_id, FULL_PERMS + [CUSTOMERS_VIEW])
    body = reader.get(f"{PROJECTS_BASE}/{project['id']}").json()

    assert body["customer_id"] == lead["customer_id"]
    assert body["customer_name"].startswith("zzt Gamuda Builders")
    assert body["customer_phone"] == "012-345 6789"
    assert body["customer_attn"] == "Lim Wei Ming"


def test_the_picked_customer_wins_over_the_leads_buyer(api):
    client, _db, _company_id, _user_id = api
    lead = _create_lead(
        client,
        new_customer={"customer_name": f"zzt Lead Buyer {uuid.uuid4().hex[:8]}"},
    ).json()
    assert lead["customer_id"] != _REGISTER_CUSTOMER["id"]

    project = _register(client, lead_id=lead["id"]).json()
    body = client.get(f"{PROJECTS_BASE}/{project['id']}").json()

    assert body["customer_id"] == _REGISTER_CUSTOMER["id"]


def test_an_older_project_with_no_picked_customer_reads_its_leads_buyer(api):
    client, db, _company_id, _user_id = api
    lead = _create_lead(
        client,
        new_customer={"customer_name": f"zzt Older Buyer {uuid.uuid4().hex[:8]}"},
    ).json()
    project = _register(client, lead_id=lead["id"]).json()
    _registered_before_v2(db, project["id"])

    body = client.get(f"{PROJECTS_BASE}/{project['id']}").json()

    assert body["customer_id"] == lead["customer_id"]
    assert body["customer_name"].startswith("zzt Older Buyer")


def test_a_project_with_no_picked_customer_and_no_lead_has_no_customer(api):
    client, db, _company_id, _user_id = api
    project = _register(client).json()
    _registered_before_v2(db, project["id"])
    body = client.get(f"{PROJECTS_BASE}/{project['id']}").json()

    assert body["customer_id"] is None
    assert body["customer_name"] is None
    assert body["customer_phone"] is None
    assert body["customer_attn"] is None


def test_the_list_carries_the_customer_too(api):
    client, _db, _company_id, _user_id = api
    lead = _create_lead(
        client,
        new_customer={"customer_name": f"zzt List Buyer {uuid.uuid4().hex[:8]}"},
    ).json()
    project = _register(client, lead_id=lead["id"], customer_id=lead["customer_id"]).json()

    rows = client.get(f"{PROJECTS_BASE}/", params={"limit": 200}).json()["data"]
    row = next(r for r in rows if r["id"] == project["id"])
    assert row["customer_name"].startswith("zzt List Buyer")


def test_phone_and_contact_need_the_customers_view_grant(api):
    """Security review, 13 Oct: the customer master's phone and main contact sit behind
    order_management.customers.view, so a project reader without it sees the name only."""
    client, db, company_id, _user_id = api
    lead = _create_lead(
        client,
        new_customer={
            "customer_name": f"zzt Gated Buyer {uuid.uuid4().hex[:8]}",
            "phone_number": "+60 11-111 1111",
        },
    ).json()
    db.add(
        CustomerContact(
            company_id=company_id,
            customer_id=lead["customer_id"],
            full_name="Hidden Contact",
            contact_role="main",
        )
    )
    db.flush()
    project = _register(client, lead_id=lead["id"], customer_id=lead["customer_id"]).json()

    body = client.get(f"{PROJECTS_BASE}/{project['id']}").json()
    assert body["customer_name"].startswith("zzt Gated Buyer")
    assert body["customer_phone"] is None
    assert body["customer_attn"] is None
