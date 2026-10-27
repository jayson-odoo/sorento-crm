"""PORTAL-P2-ONLY-THEIRS: opportunities, sample requests, NPA, conversations (UAC 1-5, 7).

Each module: a `view_own` holder's list holds only their rows, a foreign row is 404 on
reads and writes, and a `view` holder is unchanged. Behaviour card examples 2, 3 and 4.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.base import company_scope
from app.models.chat_history import ChatHistory
from app.models.new_product_application import NewProductApplication
from app.models.sales import SalesOpportunity
from app.models.sample_request import SampleRequest

from ._own_scope_support import MARKER, acting, uid, user, world
from ._pg_fixture import blank_session

OPP = "/api/v1/sales/opportunities"
SR = "/api/v1/project-sales/sample-requests"
NPA = "/api/v1/procurement/new-product-applications"
CONV = "/api/v1/sla-management/conversations"


@pytest.fixture()
def scene():
    from app.services import project_seed_service
    from app.services.sales import sales_seed_service

    with blank_session() as db:
        w = world(db)
        # Status graphs: CI's database is empty (sample requests seed with projects).
        project_seed_service.run(db, company_id=w.company_id)
        sales_seed_service.run(db)
        with company_scope(db, frozenset({w.company_id})):
            yield db, w


# ------------------------------------------------------------------ opportunities (example 2)

OPP_VIEW, OPP_OWN = "sales.opportunities.view", "sales.opportunities.view_own"
OPP_LIMITED = {OPP_OWN, "sales.opportunities.add", "sales.opportunities.edit", "sales.opportunities.delete"}


def _opportunity(db, w, agent_id, customer_id, prospect_name=None) -> str:
    from app.services import status_service
    from app.services.sales.opportunity_service import SALES_OPPORTUNITY_ENTITY

    row = SalesOpportunity(
        id=uid(), company_id=w.company_id, opportunity_no=f"{MARKER}-{uid()[:8]}",
        title=f"{MARKER} opportunity", customer_id=customer_id, sales_agent_id=agent_id,
        prospect_name=prospect_name if customer_id is None else None,
        status_id=status_service.initial_status(db, SALES_OPPORTUNITY_ENTITY).id,
        expected_amount=1000, expected_close_date=date.today() + timedelta(days=30), source="crm",
    )
    db.add(row)
    db.flush()
    return row.id


def _opp_ids(client, **params) -> set:
    response = client.get(OPP, params={"limit": 200, **params})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["data"]}


def test_opportunities_limited_list_and_detail(scene):
    db, w = scene
    o1 = _opportunity(db, w, w.ag_a.id, w.cust_a.id)
    o2 = _opportunity(db, w, w.ag_b.id, w.cust_b.id)
    with acting(db, w.a, OPP_LIMITED) as client:
        assert _opp_ids(client) == {o1}
        assert _opp_ids(client, sales_agent_id=w.ag_b.id) == set()
        assert client.get(f"{OPP}/{o1}").status_code == 200
        assert client.get(f"{OPP}/{o2}").status_code == 404
        assert client.get(f"{OPP}/{o2}/sales-order-options").status_code == 404
        assert client.patch(f"{OPP}/{o2}", json={"title": "x"}).status_code == 404
        assert client.delete(f"{OPP}/{o2}").status_code == 404


def test_opportunity_pickers_offer_only_their_customers_and_agents(scene):
    db, w = scene
    with acting(db, w.a, OPP_LIMITED) as client:
        customers = client.get(f"{OPP}/customer-options", params={"q": MARKER}).json()["items"]
        assert {c["customer_id"] for c in customers} == {w.cust_a.id}
        agents = client.get(f"{OPP}/agent-options").json()["data"]
        assert {a["id"] for a in agents} == {w.ag_a.id}


def test_opportunities_unchanged_for_a_view_holder(scene):
    db, w = scene
    o1 = _opportunity(db, w, w.ag_a.id, w.cust_a.id)
    o2 = _opportunity(db, w, w.ag_b.id, w.cust_b.id)
    with acting(db, w.a, {OPP_VIEW, OPP_OWN}) as client:
        assert {o1, o2} <= _opp_ids(client)
        assert client.get(f"{OPP}/{o2}").status_code == 200


def test_opportunities_with_no_contact_are_empty(scene):
    db, w = scene
    _opportunity(db, w, w.ag_a.id, w.cust_a.id)
    loner = user(db, "No contact")
    with acting(db, loner, OPP_LIMITED) as client:
        assert _opp_ids(client) == set()


# ------------------------------------------------------------------ sample requests (example 3)

SR_VIEW, SR_OWN = "projects.sample_requests.view", "projects.sample_requests.view_own"
SR_CREATE = "projects.sample_requests.create"


def _sample_request(db, w, *, salesperson_id=None, contact_id=None) -> str:
    from app.services import sample_request_service as svc

    row = SampleRequest(
        id=uid(), company_id=w.company_id, request_no=f"{MARKER}-{uid()[:8]}",
        salesperson_id=salesperson_id, contact_id=contact_id,
        status_id=svc._statuses(db)[svc.DRAFT].id,
    )
    db.add(row)
    db.flush()
    return row.id


def _sr_ids(client) -> set:
    response = client.get(SR, params={"status": "draft", "limit": 200})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["data"]}


def test_sample_requests_limited_list_holds_own_and_their_contacts(scene):
    db, w = scene
    s1 = _sample_request(db, w, salesperson_id=w.a)
    s2 = _sample_request(db, w, contact_id=w.ca.id)
    s3 = _sample_request(db, w, salesperson_id=w.b)
    with acting(db, w.a, {SR_OWN}) as client:
        assert _sr_ids(client) == {s1, s2}
        assert client.get(f"{SR}/{s1}").status_code == 200
        assert client.get(f"{SR}/{s2}").status_code == 200
        assert client.get(f"{SR}/{s3}").status_code == 404
        assert client.get(f"{SR}/{s3}/pdf").status_code == 404


def test_sample_request_writes_on_a_foreign_row_are_404(scene):
    db, w = scene
    s3 = _sample_request(db, w, salesperson_id=w.b)
    with acting(db, w.a, {SR_OWN, SR_CREATE}) as client:
        assert client.put(f"{SR}/{s3}", json={}).status_code == 404
        assert client.post(f"{SR}/{s3}/submit").status_code == 404
        assert client.post(f"{SR}/{s3}/move", json={"to": "processing"}).status_code == 404


def test_sample_requests_create_only_holder_keeps_todays_403(scene):
    """Owner ruling Q5a: nothing changes for anyone who does not hold view_own."""
    db, w = scene
    s3 = _sample_request(db, w, salesperson_id=w.b)
    with acting(db, w.a, {SR_CREATE}) as client:
        assert client.get(f"{SR}/{s3}").status_code == 403


def test_sample_requests_unchanged_for_a_view_holder(scene):
    db, w = scene
    s3 = _sample_request(db, w, salesperson_id=w.b)
    with acting(db, w.a, {SR_VIEW, SR_OWN}) as client:
        assert s3 in _sr_ids(client)
        assert client.get(f"{SR}/{s3}").status_code == 200


# ------------------------------------------------------------------ NPA

NPA_VIEW, NPA_OWN = "procurement.new_product_applications.view", "procurement.new_product_applications.view_own"
NPA_CREATE = "procurement.new_product_applications.create"


def _npa(db, w, *, applicant_id=None, contact_id=None) -> str:
    row = NewProductApplication(
        id=uid(), company_id=w.company_id, application_no=f"{MARKER}-{uid()[:8]}",
        applicant_id=applicant_id, contact_id=contact_id,
        source="portal" if contact_id else "staff",
    )
    db.add(row)
    db.flush()
    return row.id


def _npa_ids(client) -> set:
    response = client.get(NPA, params={"limit": 200})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["items"]}


def test_npa_limited_list_and_detail(scene):
    db, w = scene
    n1 = _npa(db, w, applicant_id=w.a)
    n2 = _npa(db, w, contact_id=w.ca.id)
    n3 = _npa(db, w, applicant_id=w.b)
    with acting(db, w.a, {NPA_OWN}) as client:
        assert _npa_ids(client) == {n1, n2}
        assert client.get(f"{NPA}/{n1}").status_code == 200
        assert client.get(f"{NPA}/{n2}").status_code == 200
        assert client.get(f"{NPA}/{n3}").status_code == 404


def test_npa_writes_on_a_foreign_row_are_404(scene):
    db, w = scene
    n3 = _npa(db, w, applicant_id=w.b)
    with acting(db, w.a, {NPA_OWN, NPA_CREATE}) as client:
        assert client.put(f"{NPA}/{n3}", json={}).status_code == 404
        assert client.post(f"{NPA}/{n3}/submit").status_code == 404
        assert client.post(f"{NPA}/{n3}/cancel", json={"reason": "x"}).status_code == 404


def test_npa_create_only_holder_keeps_todays_403(scene):
    db, w = scene
    n3 = _npa(db, w, applicant_id=w.b)
    with acting(db, w.a, {NPA_CREATE}) as client:
        assert client.get(f"{NPA}/{n3}").status_code == 403


def test_npa_unchanged_for_a_view_holder(scene):
    db, w = scene
    n3 = _npa(db, w, applicant_id=w.b)
    with acting(db, w.a, {NPA_VIEW, NPA_OWN}) as client:
        assert n3 in _npa_ids(client)
        assert client.get(f"{NPA}/{n3}").status_code == 200


# ------------------------------------------------------------------ conversations (example 4)

CONV_VIEW, CONV_OWN = "sla_management.conversations.view", "sla_management.conversations.view_own"
CONV_REPLY = "sla_management.conversations.reply"


def _message(db, contact_row, text: str) -> None:
    db.add(
        ChatHistory(
            channel="whatsapp", contact_id=contact_row.respond_io_id,
            phone_number=contact_row.phone_number, message=text,
            sent_at=datetime.utcnow(), type="incoming",
        )
    )
    db.flush()


def _inbox(client, tab="all", q=MARKER) -> set:
    response = client.get(CONV, params={"tab": tab, "q": q, "limit": 100})
    assert response.status_code == 200, response.text
    return {row["respond_io_id"] for row in response.json()["items"]}


def test_conversations_limited_inbox_lists_only_their_customers_contacts(scene):
    db, w = scene
    _message(db, w.k1, "hello one")
    _message(db, w.k2, "hello two")
    with acting(db, w.a, {CONV_OWN}) as client:
        assert _inbox(client) == {w.k1.respond_io_id}
        for tab in ("mine", "mentioned", "unassigned"):
            assert w.k2.respond_io_id not in _inbox(client, tab=tab), tab


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", "page"),
        ("GET", "search?q=x"),
        ("GET", "comments"),
        ("GET", "window"),
        ("GET", "media?url=https://example.com/x.png"),
        ("POST", "comments"),
        ("POST", "reply"),
        ("POST", "template-message"),
    ],
)
def test_conversations_foreign_contact_is_404_on_every_thread_route(scene, method, suffix):
    db, w = scene
    _message(db, w.k2, "hello two")
    with acting(db, w.a, {CONV_OWN, CONV_REPLY}) as client:
        response = client.request(method, f"{CONV}/{w.k2.id}/{suffix}", json={"body": "x", "text": "x", "template_id": uid(), "params": {}})
        assert response.status_code == 404, response.text


def test_conversations_own_contact_comments_open(scene):
    db, w = scene
    _message(db, w.k1, "hello one")
    with acting(db, w.a, {CONV_OWN}) as client:
        assert client.get(f"{CONV}/{w.k1.id}/comments").status_code == 200


def test_conversations_reply_still_needs_reply(scene):
    db, w = scene
    _message(db, w.k1, "hello one")
    with acting(db, w.a, {CONV_OWN}) as client:
        assert client.post(f"{CONV}/{w.k1.id}/reply", json={"text": "x"}).status_code == 403


def test_conversations_unchanged_for_a_view_holder(scene):
    db, w = scene
    _message(db, w.k1, "hello one")
    _message(db, w.k2, "hello two")
    with acting(db, w.a, {CONV_VIEW, CONV_OWN}) as client:
        assert {w.k1.respond_io_id, w.k2.respond_io_id} <= _inbox(client)
        assert client.get(f"{CONV}/{w.k2.id}/comments").status_code == 200


def test_conversations_with_no_contact_are_empty(scene):
    db, w = scene
    _message(db, w.k1, "hello one")
    loner = user(db, "No contact")
    with acting(db, loner, {CONV_OWN}) as client:
        assert _inbox(client) == set()


# ------------------------------------------------------------------ security review H1, H2


def _sales_order(db, w, customer_id) -> str:
    from app.models.order import SalesOrder

    row = SalesOrder(
        id=uid(), company_id=w.company_id, so_number=f"ZZT-SO-{uid()[:6]}",
        customer_id=customer_id, status="open", order_date=date.today(),
    )
    db.add(row)
    db.flush()
    return row.id


def test_sales_order_options_offer_only_their_customers_orders(scene):
    """H1: a prospect opportunity (no customer) searched every order in the company."""
    db, w = scene
    mine = _sales_order(db, w, w.cust_a.id)
    theirs = _sales_order(db, w, w.cust_b.id)
    prospect = _opportunity(db, w, w.ag_a.id, None, prospect_name=f"{MARKER} prospect")
    with acting(db, w.a, OPP_LIMITED) as client:
        response = client.get(f"{OPP}/{prospect}/sales-order-options")
        assert response.status_code == 200, response.text
        ids = {row["id"] for row in response.json()["data"]}
        assert mine in ids and theirs not in ids
    with acting(db, w.a, {OPP_VIEW}) as client:
        ids = {row["id"] for row in client.get(f"{OPP}/{prospect}/sales-order-options").json()["data"]}
        assert {mine, theirs} <= ids


def test_a_limited_user_cannot_point_their_opportunity_at_a_foreign_customer(scene):
    db, w = scene
    o1 = _opportunity(db, w, w.ag_a.id, w.cust_a.id)
    with acting(db, w.a, OPP_LIMITED) as client:
        response = client.patch(f"{OPP}/{o1}", json={"customer_id": w.cust_b.id})
        assert response.status_code == 403, response.text


def _park(client, action_key, entity_type, entity_id, payload=None):
    return client.post(
        "/api/v1/pending-actions",
        json={"action_key": action_key, "entity_type": entity_type, "entity_id": entity_id, "payload": payload or {}},
    )


def test_a_limited_user_cannot_park_a_delete_on_a_foreign_opportunity(scene):
    """H2: the screen deletes through a deferred action, not DELETE /{id}."""
    db, w = scene
    o2 = _opportunity(db, w, w.ag_b.id, w.cust_b.id)
    with acting(db, w.a, OPP_LIMITED) as client:
        response = _park(client, "sales_opportunity.delete", "sales_opportunity", o2)
        assert response.status_code == 404, response.text


def test_a_parked_delete_rechecks_when_it_runs(scene):
    from app.services.error_handler import AppException
    from app.services.record_actions import _delete_sales_opportunity

    db, w = scene
    o2 = _opportunity(db, w, w.ag_b.id, w.cust_b.id)
    with acting(db, w.a, OPP_LIMITED):
        with pytest.raises(AppException) as exc:
            _delete_sales_opportunity(db, {"entity_id": o2, "requested_by_id": w.a})
        assert exc.value.status_code == 404
    assert db.get(SalesOpportunity, o2) is not None


def test_fulfilment_undo_follows_its_own_slug_but_line_files_stay_refused(scene):
    """Q2: undo confirm belongs to fulfilment planning, so it follows its own slug (edit);
    sales-order line files are not a cross-project screen and stay refused."""
    db, w = scene
    with acting(db, w.a, {"projects.projects.view_own", "projects.projects.edit"}) as client:
        response = _park(
            client, "project_sales_order.undo_confirm", "project_sales_order", uid(),
            {"decision_id": uid()},
        )
        assert "your own records only" not in response.text, response.text
        response = _park(
            client, "sales_order_line_attachment.delete", "sales_order_line_attachment", uid(),
            {"line_id": uid()},
        )
        assert response.status_code == 403, response.text


def test_a_limited_project_user_cannot_file_a_sample_request_on_a_foreign_project(scene):
    """Owner ruling Q4a; reviewer kill test M15."""
    from app.models.projects import Project

    db, w = scene
    foreign = Project(
        id=uid(), company_id=w.company_id, project_code=f"{MARKER}-{uid()[:6]}",
        title=f"{MARKER} foreign {uid()[:6]}", normalised_title=f"{MARKER} foreign {uid()[:6]}",
        owner_user_id=w.b,
    )
    db.add(foreign)
    db.flush()
    perms = {"projects.projects.view_own", SR_OWN, SR_CREATE}
    with acting(db, w.a, perms) as client:
        response = client.post(SR, json={"project_id": foreign.id})
        assert response.status_code == 422, response.text
        assert "SAMPLE_REQUEST_PROJECT_INVALID" in response.text


# ------------------------------------------------------------------ list layout (browser pass finding)


def test_a_view_own_holder_reads_their_own_column_layout_but_not_shared_saved_views(scene):
    """The opportunity grid loads its column layout from `/list-query/column-config/<view slug>`;
    without this a view_own holder's grid never rendered (sandbox browser pass, 27 Oct). Saved
    views are shared across users, so they stay on the plain `view` slug."""
    from app.api.v1.list_query import _can_view_listing_key
    from app.models.user import UserPermission

    db, w = scene
    for slug in (OPP_VIEW, OPP_OWN):
        if not db.query(UserPermission).filter(UserPermission.slug == slug).first():
            db.add(UserPermission(id=uid(), slug=slug, name=slug))
    db.flush()
    with acting(db, w.a, {OPP_OWN}) as client:
        assert client.get(f"/api/v1/list-query/column-config/{OPP_VIEW}").status_code == 200
        assert _can_view_listing_key(db, w.a, OPP_VIEW, fail_closed=True) is False
    with acting(db, w.a, set()) as client:
        assert client.get(f"/api/v1/list-query/column-config/{OPP_VIEW}").status_code == 403
