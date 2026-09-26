"""S2: opportunities logged by salespeople, CRM side and shared seeds.

Plan: documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md, sections 3.4, 3.7 and
section 16 (the S2 build contract). UAC:
sales-targets-opportunities-26sep-acceptance-criteria.md, S2-1, S2-2, S2-7 to S2-9, S2-15, S2-16.

Route level on purpose, same reasoning as tests/test_sales_teams_s6.py: the permission gate, the
module mount at `/sales` and the company scope are all part of what S2 promises and a
service-only test reaches none of them.

Nothing here exists yet on this branch (no `app.models.sales.SalesOpportunity`, no
`app.services.sales.sales_seed_service`, no `/api/v1/sales/opportunities` router): every test is
expected to fail on collection or at the first call, for exactly that reason (ImportError,
AttributeError or 404), never for an unrelated fixture bug.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.company import Company
from app.models.sales_agent import SalesAgent
from app.models.base import company_scope

from ._pg_fixture import blank_session

BASE = "/api/v1/sales/opportunities"

ALL = [
    "sales.opportunities.view",
    "sales.opportunities.add",
    "sales.opportunities.edit",
    "sales.opportunities.delete",
]


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _agent(db, code: str, name: str, *, company_id=None, active=True) -> SalesAgent:
    row = SalesAgent(
        id=_uid(),
        sales_agent=f"ZZO{code}-{_uid()[:6]}".upper(),
        description=name,
        is_active=active,
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


def _product(db, *, name: str = "ZZT Opp Product"):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:6]}", category_name="ZZT Opp Category"
    )
    brand = Brand(id=_uid(), brand_code=f"ZZT-{_uid()[:6]}", brand_name="ZZT Opp Brand")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT-{_uid()[:6]}", uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:6]}",
        product_name=name,
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    return product


def _customer(db, company_id, *, name: str = "ZZT Opp Customer", agent_id=None):
    from app.models.order import Customer

    customer = Customer(
        id=_uid(),
        company_id=company_id,
        customer_code=f"ZZT-{_uid()[:6]}",
        customer_name=name,
        sales_agent_id=agent_id,
    )
    db.add(customer)
    db.flush()
    return customer


def _sales_order(db, company_id, customer_id, *, status: str = "open", so_number=None):
    from app.models.order import SalesOrder

    order = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=so_number or f"ZZT-{_uid()[:6]}",
        customer_id=customer_id,
        status=status,
        order_date=date(2026, 10, 1),
    )
    db.add(order)
    db.flush()
    return order


def _client(db, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user_id = _uid()
    actor = {"id": user_id, "email": f"{user_id}@zzo.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture
def world():
    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            yield db, company_id


@pytest.fixture
def api(world):
    """A full-permission client, with the S2 status graph and lost-reason lookup seeded.

    Almost every CRM test needs a `new`/`won`/`lost` graph to create against, so the seed runs
    once here rather than being repeated in every test.
    """
    from app.services.audit_service import register_audit_listeners
    from app.services.sales import sales_seed_service

    db, company_id = world
    sales_seed_service.run(db)
    db.flush()
    # A bare `TestClient(app)` (no `with`) never runs the app's startup event, so the
    # audit listener is not registered unless something else in this run already did -
    # same reasoning `test_board_undo_last_confirm.py` documents at its own call site.
    register_audit_listeners()
    client, originals = _client(db, ALL)
    try:
        yield client, db, company_id
    finally:
        _restore(originals)


def _status_id(db, key: str) -> str:
    from app.models.status import Status

    return (
        db.query(Status)
        .filter(Status.entity_type == "sales_opportunity", Status.key == key)
        .one()
        .id
    )


def _create(
    client,
    *,
    customer_id=None,
    prospect_name=None,
    title="ZZT Opportunity",
    amount="1000.00",
    close_date="2026-11-01",
    lines=None,
):
    payload = {"title": title, "expected_amount": amount, "expected_close_date": close_date}
    if customer_id:
        payload["customer_id"] = customer_id
    if prospect_name:
        payload["prospect_name"] = prospect_name
    if lines is not None:
        payload["lines"] = lines
    res = client.post(BASE, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# S2-1: the default status graph, lost reasons, numbering rule, seeded once
# --------------------------------------------------------------------------- #


def test_s2_1_graph_seeded_once_with_proposal_inactive(world):
    from app.models.status import Status, StatusTransition
    from app.services.sales import sales_seed_service

    db, _ = world
    sales_seed_service.run(db)
    db.flush()

    statuses = {
        s.key: s
        for s in db.query(Status)
        .filter(Status.entity_type == "sales_opportunity", Status.scope_id.is_(None))
        .all()
    }
    assert set(statuses) == {"new", "qualified", "proposal", "negotiation", "won", "lost"}
    assert statuses["new"].is_initial is True
    assert statuses["new"].is_default is True
    assert float(statuses["new"].win_probability) == 10
    assert float(statuses["qualified"].win_probability) == 25
    assert float(statuses["proposal"].win_probability) == 50
    assert statuses["proposal"].is_active is False
    assert float(statuses["negotiation"].win_probability) == 75
    assert statuses["won"].is_terminal is True
    assert float(statuses["won"].win_probability) == 100
    assert statuses["lost"].is_terminal is True
    assert float(statuses["lost"].win_probability) == 0

    edges = {
        (t.from_status_id, t.to_status_id)
        for t in db.query(StatusTransition)
        .filter(
            StatusTransition.entity_type == "sales_opportunity",
            StatusTransition.scope_id.is_(None),
        )
        .all()
    }
    k = statuses
    expected = {
        (k["new"].id, k["qualified"].id),
        (k["qualified"].id, k["proposal"].id),
        (k["proposal"].id, k["negotiation"].id),
        (k["qualified"].id, k["negotiation"].id),
        (k["qualified"].id, k["new"].id),
        (k["proposal"].id, k["qualified"].id),
        (k["negotiation"].id, k["proposal"].id),
        (k["negotiation"].id, k["qualified"].id),
        (k["new"].id, k["won"].id),
        (k["new"].id, k["lost"].id),
        (k["qualified"].id, k["won"].id),
        (k["qualified"].id, k["lost"].id),
        (k["proposal"].id, k["won"].id),
        (k["proposal"].id, k["lost"].id),
        (k["negotiation"].id, k["won"].id),
        (k["negotiation"].id, k["lost"].id),
    }
    assert edges == expected

    # A second startup adds nothing (the wholesale guard).
    before = db.query(Status).filter(Status.entity_type == "sales_opportunity").count()
    sales_seed_service.run(db)
    db.flush()
    after = db.query(Status).filter(Status.entity_type == "sales_opportunity").count()
    assert after == before

    # An admin's rename survives a later restart.
    statuses["won"].label = "Closed Won"
    db.flush()
    sales_seed_service.run(db)
    db.flush()
    db.expire_all()
    won = (
        db.query(Status)
        .filter(Status.entity_type == "sales_opportunity", Status.key == "won")
        .one()
    )
    assert won.label == "Closed Won"


def test_s2_1_lost_reasons_lookup_has_five_options(world):
    from app.models.lookup import LookupOption, LookupSet
    from app.services.sales import sales_seed_service

    db, _ = world
    sales_seed_service.run(db)
    db.flush()

    lookup_set = (
        db.query(LookupSet).filter(LookupSet.set_key == "sales_opportunity_lost_reasons").one()
    )
    options = db.query(LookupOption).filter(LookupOption.set_id == lookup_set.id).all()
    assert len(options) == 5


def test_s2_1_numbering_rule_is_opp_prefix_six_digits(world):
    from app.models.numbering import DocumentNumberingRule
    from app.services.sales import sales_seed_service

    db, _ = world
    sales_seed_service.run(db)
    db.flush()

    rule = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == "sales_opportunity")
        .one()
    )
    assert rule.prefix_template == "OPP-"
    assert rule.number_digits == 6


def test_s2_1_entity_is_registered_with_the_status_engine():
    from app.status_engine.discovery import register_module_entities
    from app.status_engine.registry import get_status_entity

    register_module_entities()
    entity = get_status_entity("sales_opportunity")
    assert entity is not None


# --------------------------------------------------------------------------- #
# S2-2: Proposal is optional, and renaming a key stage keeps its semantics
# --------------------------------------------------------------------------- #


def test_s2_2_move_to_proposal_needs_it_active_first(api):
    from app.models.status import Status

    client, db, company_id = api
    customer = _customer(db, company_id)
    created = _create(client, customer_id=customer.id)

    qualified_id = _status_id(db, "qualified")
    assert client.patch(f"{BASE}/{created['id']}", json={"status_id": qualified_id}).status_code == 200

    proposal = (
        db.query(Status)
        .filter(Status.entity_type == "sales_opportunity", Status.key == "proposal")
        .one()
    )
    res = client.patch(f"{BASE}/{created['id']}", json={"status_id": proposal.id})
    assert res.status_code == 422, res.text

    proposal.is_active = True
    db.flush()
    res2 = client.patch(f"{BASE}/{created['id']}", json={"status_id": proposal.id})
    assert res2.status_code == 200, res2.text
    assert res2.json()["stage_key"] == "proposal"


def test_s2_2_renaming_wons_label_still_sets_outcome_won(api):
    from app.models.status import Status

    client, db, company_id = api
    won = (
        db.query(Status)
        .filter(Status.entity_type == "sales_opportunity", Status.key == "won")
        .one()
    )
    won.label = "Closed Won"
    db.flush()
    customer = _customer(db, company_id)
    created = _create(client, customer_id=customer.id)

    res = client.patch(f"{BASE}/{created['id']}", json={"status_id": won.id})
    assert res.status_code == 200, res.text
    assert res.json()["outcome"] == "won"
    assert res.json()["stage_label"] == "Closed Won"


# --------------------------------------------------------------------------- #
# S2-7: CRM create stamps the customer's agent; Won/Lost rules
# --------------------------------------------------------------------------- #


def test_s2_7_create_stamps_the_customers_agent_and_null_agent_customer_gives_null(api):
    client, db, company_id = api
    agent = _agent(db, "A", "Agent A")
    with_agent = _customer(db, company_id, name="ZZT With Agent", agent_id=agent.id)
    no_agent = _customer(db, company_id, name="ZZT No Agent")

    created = _create(client, customer_id=with_agent.id, title="ZZT Opp A")
    assert created["sales_agent_id"] == agent.id
    assert created["source"] == "crm"
    assert created["opportunity_no"].startswith("OPP-")
    assert created["stage_key"] == "new"
    assert created["outcome"] == "open"

    created2 = _create(client, customer_id=no_agent.id, title="ZZT Opp B")
    assert created2["sales_agent_id"] is None


def test_s2_7_won_with_sales_order_of_the_same_customer_succeeds(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    order = _sales_order(db, company_id, customer.id)
    created = _create(client, customer_id=customer.id)

    won_id = _status_id(db, "won")
    res = client.patch(
        f"{BASE}/{created['id']}", json={"status_id": won_id, "sales_order_id": order.id}
    )
    assert res.status_code == 200, res.text
    assert res.json()["outcome"] == "won"
    assert res.json()["sales_order_id"] == order.id


def test_s2_7_won_with_another_customers_sales_order_is_422(api):
    client, db, company_id = api
    customer = _customer(db, company_id, name="ZZT Mine")
    other = _customer(db, company_id, name="ZZT Theirs")
    other_order = _sales_order(db, company_id, other.id)
    created = _create(client, customer_id=customer.id)

    won_id = _status_id(db, "won")
    res = client.patch(
        f"{BASE}/{created['id']}", json={"status_id": won_id, "sales_order_id": other_order.id}
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "SALES_ORDER_OTHER_CUSTOMER"


def test_s2_7_lost_needs_a_reason_from_the_lookup(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    created = _create(client, customer_id=customer.id)
    lost_id = _status_id(db, "lost")

    res = client.patch(f"{BASE}/{created['id']}", json={"status_id": lost_id})
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "LOST_REASON_REQUIRED"

    res2 = client.patch(
        f"{BASE}/{created['id']}", json={"status_id": lost_id, "lost_reason": "not_a_real_reason"}
    )
    assert res2.status_code == 422, res2.text

    res3 = client.patch(
        f"{BASE}/{created['id']}", json={"status_id": lost_id, "lost_reason": "price"}
    )
    assert res3.status_code == 200, res3.text
    assert res3.json()["outcome"] == "lost"


def test_s2_7_won_prospect_takes_the_sales_orders_customer(api):
    """Coordinator addendum (plan 3.5 / section 16, commit 54b0444e): Won with a
    `sales_order_id` on a PROSPECT (no customer) is accepted, not 422; the opportunity takes
    that order's customer and keeps `prospect_name` as history."""
    client, db, company_id = api
    customer = _customer(db, company_id, name="ZZT Became A Customer")
    order = _sales_order(db, company_id, customer.id)
    created = _create(client, prospect_name="ZZT Prospect Co", title="ZZT Prospect Opp")
    assert created["customer_id"] is None
    assert created["prospect_name"] == "ZZT Prospect Co"

    won_id = _status_id(db, "won")
    res = client.patch(
        f"{BASE}/{created['id']}", json={"status_id": won_id, "sales_order_id": order.id}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["customer_id"] == customer.id
    assert body["prospect_name"] == "ZZT Prospect Co"
    assert body["outcome"] == "won"


def test_sales_order_options_for_a_customer_opportunity_is_scoped_to_that_customer(api):
    client, db, company_id = api
    customer = _customer(db, company_id, name="ZZT Cust")
    other = _customer(db, company_id, name="ZZT Other Cust")
    mine = _sales_order(db, company_id, customer.id, so_number="ZZT-SO-MINE")
    theirs = _sales_order(db, company_id, other.id, so_number="ZZT-SO-THEIRS")
    cancelled = _sales_order(db, company_id, customer.id, status="cancelled", so_number="ZZT-SO-CANC")
    created = _create(client, customer_id=customer.id)

    res = client.get(f"{BASE}/{created['id']}/sales-order-options")
    assert res.status_code == 200, res.text
    ids = {o["id"] for o in res.json()["data"]}
    assert mine.id in ids
    assert theirs.id not in ids
    assert cancelled.id not in ids


def test_sales_order_options_for_a_prospect_searches_every_order_by_q(api):
    client, db, company_id = api
    customer = _customer(db, company_id, name="ZZT Findable Co")
    order = _sales_order(db, company_id, customer.id, so_number="ZZT-SO-FIND")
    created = _create(client, prospect_name="ZZT Some Prospect")

    res = client.get(f"{BASE}/{created['id']}/sales-order-options", params={"q": "Findable"})
    assert res.status_code == 200, res.text
    ids = {o["id"] for o in res.json()["data"]}
    assert order.id in ids


# --------------------------------------------------------------------------- #
# S2-8: list filters, RBAC, company scope, hard delete
# --------------------------------------------------------------------------- #


def test_s2_8_list_filters_status_agent_customer_close_range_and_query(api):
    client, db, company_id = api
    agent_a = _agent(db, "A", "Agent A")
    agent_b = _agent(db, "B", "Agent B")
    cust_a = _customer(db, company_id, name="ZZT Cust A", agent_id=agent_a.id)
    cust_b = _customer(db, company_id, name="ZZT Cust B", agent_id=agent_b.id)

    opp_a = _create(client, customer_id=cust_a.id, title="Alpha deal", close_date="2026-10-15")
    opp_b = _create(client, customer_id=cust_b.id, title="Beta deal", close_date="2026-11-15")

    by_agent = client.get(BASE, params={"sales_agent_id": agent_a.id}).json()["data"]
    assert {o["id"] for o in by_agent} == {opp_a["id"]}

    by_customer = client.get(BASE, params={"customer_id": cust_b.id}).json()["data"]
    assert {o["id"] for o in by_customer} == {opp_b["id"]}

    by_range = client.get(
        BASE, params={"close_from": "2026-10-01", "close_to": "2026-10-31"}
    ).json()["data"]
    assert {o["id"] for o in by_range} == {opp_a["id"]}
    # Inclusive at the edge.
    edge = client.get(
        BASE, params={"close_from": "2026-10-15", "close_to": "2026-10-15"}
    ).json()["data"]
    assert {o["id"] for o in edge} == {opp_a["id"]}

    by_query_title = client.get(BASE, params={"query": "beta"}).json()["data"]
    assert {o["id"] for o in by_query_title} == {opp_b["id"]}

    by_query_no = client.get(BASE, params={"query": opp_a["opportunity_no"]}).json()["data"]
    assert {o["id"] for o in by_query_no} == {opp_a["id"]}

    new_id = _status_id(db, "new")
    by_status = client.get(BASE, params={"status_id": new_id}).json()["data"]
    assert {opp_a["id"], opp_b["id"]} <= {o["id"] for o in by_status}

    listed = client.get(BASE).json()
    assert "data" in listed and "pagination" in listed


def test_s2_8_each_route_is_403_without_its_slug(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    created = _create(client, customer_id=customer.id, title="ZZT gate")

    routes = [
        ("get", BASE, None, "sales.opportunities.view"),
        (
            "post",
            BASE,
            {
                "customer_id": customer.id,
                "title": "ZZT Denied",
                "expected_amount": "1",
                "expected_close_date": "2026-11-01",
            },
            "sales.opportunities.add",
        ),
        ("patch", f"{BASE}/{created['id']}", {"title": "ZZT Renamed"}, "sales.opportunities.edit"),
        ("delete", f"{BASE}/{created['id']}", None, "sales.opportunities.delete"),
    ]
    for method, url, body, slug in routes:
        others = [s for s in ALL if s != slug]
        c, originals = _client(db, others)
        try:
            kwargs = {"json": body} if body is not None else {}
            res = getattr(c, method)(url, **kwargs)
        finally:
            _restore(originals)
        assert res.status_code == 403, f"{method.upper()} {url} without {slug}: {res.status_code}"


def test_s2_8_another_companys_opportunity_is_invisible(api):
    from app.models.sales import SalesOpportunity

    client, db, company_id = api
    other = Company(id=_uid(), name="ZZT Other Co", code=f"Z{_uid()[:6]}")
    db.add(other)
    db.flush()
    with company_scope(db, None):
        other_customer = _customer(db, other.id, name="ZZT Foreign Cust")
        foreign = SalesOpportunity(
            id=_uid(),
            company_id=other.id,
            opportunity_no="OPP-999999",
            customer_id=other_customer.id,
            title="ZZT Foreign Opp",
            expected_amount=Decimal("1"),
            expected_close_date=date(2026, 11, 1),
            outcome="open",
            source="crm",
        )
        db.add(foreign)
        db.flush()

    listed = [o["id"] for o in client.get(BASE).json()["data"]]
    assert foreign.id not in listed
    assert client.get(f"{BASE}/{foreign.id}").status_code == 404


def test_s2_8_delete_is_hard_and_removes_the_lines(api):
    from app.models.sales import SalesOpportunity, SalesOpportunityLine

    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    created = _create(
        client, customer_id=customer.id, title="ZZT Delete Me", lines=[{"product_id": product.id, "qty": 2}]
    )

    res = client.delete(f"{BASE}/{created['id']}")
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.query(SalesOpportunity).filter(SalesOpportunity.id == created["id"]).count() == 0
    assert (
        db.query(SalesOpportunityLine)
        .filter(SalesOpportunityLine.opportunity_id == created["id"])
        .count()
        == 0
    )


# --------------------------------------------------------------------------- #
# S2-9: every stage change is audited to the acting user (CRM side)
# --------------------------------------------------------------------------- #


def test_s2_9_crm_stage_move_is_audited_to_the_acting_user(api):
    from app.models.audit import AuditLog

    client, db, company_id = api
    customer = _customer(db, company_id)
    created = _create(client, customer_id=customer.id)
    qualified_id = _status_id(db, "qualified")

    res = client.patch(f"{BASE}/{created['id']}", json={"status_id": qualified_id})
    assert res.status_code == 200, res.text

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "sales_opportunities", AuditLog.entity_id == created["id"])
        .all()
    )
    assert rows, "expected an audit row for the stage move"
    assert any(r.user_id for r in rows)


# --------------------------------------------------------------------------- #
# S2-15: one Customer or prospect search, over ALL customers on the CRM side
# --------------------------------------------------------------------------- #


def test_s2_15_customer_options_lists_matches_and_offers_a_prospect(api):
    client, db, company_id = api
    seri = _customer(db, company_id, name="Seri Indah Renovation")

    res = client.get(f"{BASE}/customer-options", params={"q": "seri"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert any(i["customer_id"] == seri.id for i in body["items"])
    # "seri" alone is a substring match, not the exact (normalised) name.
    assert body["prospect"] == {"name": "seri"}

    exact = client.get(
        f"{BASE}/customer-options", params={"q": "  seri   INDAH renovation "}
    ).json()
    assert exact["prospect"] is None
    assert any(i["customer_id"] == seri.id for i in exact["items"])

    brand_new = client.get(
        f"{BASE}/customer-options", params={"q": "Brand New Prospect Co"}
    ).json()
    assert brand_new["prospect"] == {"name": "Brand New Prospect Co"}


def test_s2_15_prospect_matching_a_customers_name_is_422(api):
    client, db, company_id = api
    _customer(db, company_id, name="Seri Indah Renovation")

    res = client.post(
        BASE,
        json={
            "prospect_name": "  seri   INDAH renovation ",
            "title": "ZZT",
            "expected_amount": "1",
            "expected_close_date": "2026-11-01",
        },
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "PROSPECT_IS_A_CUSTOMER"


def test_s2_15_both_customer_and_prospect_together_is_422(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    res = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "prospect_name": "ZZT Both At Once",
            "title": "ZZT",
            "expected_amount": "1",
            "expected_close_date": "2026-11-01",
        },
    )
    assert res.status_code == 422, res.text


def test_s2_15_neither_customer_nor_prospect_is_422(api):
    client, db, company_id = api
    res = client.post(
        BASE, json={"title": "ZZT", "expected_amount": "1", "expected_close_date": "2026-11-01"}
    )
    assert res.status_code == 422, res.text
    assert res.json().get("code") == "CUSTOMER_OR_PROSPECT_REQUIRED"


def test_s2_15_prospect_only_creates_no_customer_row(api):
    from app.models.order import Customer

    client, db, company_id = api
    before = db.query(Customer).filter(Customer.company_id == company_id).count()

    created = _create(client, prospect_name="ZZT Never A Customer")
    assert created["prospect_name"] == "ZZT Never A Customer"
    assert created["customer_id"] is None

    after = db.query(Customer).filter(Customer.company_id == company_id).count()
    assert after == before


# --------------------------------------------------------------------------- #
# S2-16: optional product lines
# --------------------------------------------------------------------------- #


def test_s2_16_lines_are_stored_in_entered_order(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    p1 = _product(db, name="ZZT P1")
    p2 = _product(db, name="ZZT P2")
    p3 = _product(db, name="ZZT P3")

    created = _create(
        client,
        customer_id=customer.id,
        title="ZZT lines",
        lines=[
            {"product_id": p1.id, "qty": 2},
            {"product_id": p2.id, "qty": 1},
            {"product_id": p3.id, "qty": 5},
        ],
    )
    assert [l["product_id"] for l in created["lines"]] == [p1.id, p2.id, p3.id]
    assert [float(l["qty"]) for l in created["lines"]] == [2, 1, 5]
    assert all("product_code" in l and "product_name" in l for l in created["lines"])

    detail = client.get(f"{BASE}/{created['id']}").json()
    assert [l["product_id"] for l in detail["lines"]] == [p1.id, p2.id, p3.id]


@pytest.mark.parametrize("bad_qty", [0, -1])
def test_s2_16_qty_zero_or_negative_is_422(api, bad_qty):
    client, db, company_id = api
    customer = _customer(db, company_id)
    product = _product(db)
    res = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "title": "ZZT",
            "expected_amount": "1",
            "expected_close_date": "2026-11-01",
            "lines": [{"product_id": product.id, "qty": bad_qty}],
        },
    )
    assert res.status_code == 422, (bad_qty, res.text)


def test_s2_16_zero_lines_is_valid(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    created = _create(client, customer_id=customer.id, title="ZZT no lines", lines=[])
    assert created["lines"] == []


def test_s2_16_expected_amount_is_required(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    res = client.post(
        BASE,
        json={
            "customer_id": customer.id,
            "title": "ZZT no amount",
            "expected_close_date": "2026-11-01",
        },
    )
    assert res.status_code == 422, res.text


def test_s2_16_patch_replaces_the_line_set(api):
    client, db, company_id = api
    customer = _customer(db, company_id)
    p1 = _product(db, name="ZZT P1")
    p2 = _product(db, name="ZZT P2")
    created = _create(
        client, customer_id=customer.id, lines=[{"product_id": p1.id, "qty": 1}]
    )

    res = client.patch(
        f"{BASE}/{created['id']}", json={"lines": [{"product_id": p2.id, "qty": 9}]}
    )
    assert res.status_code == 200, res.text
    assert [l["product_id"] for l in res.json()["lines"]] == [p2.id]
    assert [float(l["qty"]) for l in res.json()["lines"]] == [9]


# --------------------------------------------------------------------------- #
# Purge and permission registry (section 16: both tables join PURGE_ORDER and
# purge_tables.json; the four slugs are registered)
# --------------------------------------------------------------------------- #


def test_purge_order_has_opportunity_lines_before_opportunities():
    from app.models.sales import SalesOpportunity, SalesOpportunityLine
    from app.modules.sales.purge import PURGE_ORDER

    assert SalesOpportunityLine in PURGE_ORDER
    assert SalesOpportunity in PURGE_ORDER
    assert PURGE_ORDER.index(SalesOpportunityLine) < PURGE_ORDER.index(SalesOpportunity)


def test_frontend_purge_manifest_lists_the_opportunity_tables():
    import json
    from pathlib import Path

    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "sorento_crm_frontend"
        / "modules"
        / "sales"
        / "purge_tables.json"
    )
    manifest = json.loads(manifest_path.read_text())
    assert "sales.opportunities" in manifest["tables"]
    assert "sales.opportunity_lines" in manifest["tables"]


def test_permission_slugs_are_registered():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    slugs = {p["slug"] for p in PERMISSION_REGISTRY}
    assert {
        "sales.opportunities.view",
        "sales.opportunities.add",
        "sales.opportunities.edit",
        "sales.opportunities.delete",
    } <= slugs
