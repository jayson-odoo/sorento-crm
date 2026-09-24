"""Assign a sales agent to a customer (#1170 slice 1, small fix track).

`customers.sales_agent_id` already existed (read by the portal debtor dropdown), but nothing
on the CRM side could set it: `CustomerUpdate`/`CustomerCreate` did not carry the field and
`CustomerResponse` did not carry it either - the classic drop, since `response_model` silently
strips anything not declared on the schema even when the ORM row has it. Guarded here by
route-level tests (below the service-level ones) that serialize through the real endpoint,
not just the ORM object the service hands back (PR #1177 review, blocking item 2).

Company matters twice, and differently each time:

- **Which agents to OFFER** (`GET /customers/sales-agents-select`) is the caller's company
  scope: `sales_agent_service.scope_filter` (shared agents, `company_id IS NULL`, plus
  whatever companies the caller can see).
- **Which agent may be ASSIGNED to one customer** (`CustomerService._resolve_sales_agent`)
  is the CUSTOMER's own `company_id`, not the caller's scope - a caller scoped to companies
  {A, B} must not be able to use that breadth to link a B-owned agent onto an A customer
  (PR #1177 review, security item 3).
"""
from __future__ import annotations

import uuid

import pytest

from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
# (see tests/test_orders_so_outstanding.py for the same note).
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.schemas.order import CustomerCreate, CustomerUpdate
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.company_scope_resolver import apply_company_scope
from app.services.error_handler import AppException
from app.services.order_service import CustomerService
from app.services.scm import sales_agent_service
from app.services.user_service import UserPermissionService

from ._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _customer(session, service: CustomerService) -> Customer:
    return service.create_customer(
        CustomerCreate(customer_code=unique_code("C")[:50], customer_name="Delta Hardware")
    )


def _agent(session, *, company_id=None, code: str = "AGT", active: bool = True) -> SalesAgent:
    agent = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=unique_code(code)[:50],
        person_label="Sean Tan",
        company_id=company_id,
        is_active=active,
    )
    session.add(agent)
    session.flush()
    return agent


# ------------------------------------------------------------------ persistence + shape


def test_a_valid_agent_persists_and_the_response_carries_id_code_and_name():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)
        agent = _agent(session)

        updated = service.update_customer(
            str(customer.id), CustomerUpdate(sales_agent_id=agent.id)
        )
        assert str(updated.sales_agent_id) == str(agent.id)

        fetched = service.get_customer(str(customer.id))
        assert str(fetched.sales_agent_id) == str(agent.id)
        assert fetched.sales_agent_code == agent.sales_agent
        assert fetched.sales_agent_name == agent.person_label


def test_an_unknown_agent_id_is_rejected_with_422():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)

        with pytest.raises(AppException) as exc:
            service.update_customer(
                str(customer.id), CustomerUpdate(sales_agent_id=str(uuid.uuid4()))
            )
        assert exc.value.status_code == 422


def test_a_malformed_agent_id_reads_as_422_not_a_500():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)

        with pytest.raises(AppException) as exc:
            service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id="not-a-uuid"))
        assert exc.value.status_code == 422


def test_an_empty_string_agent_id_on_update_is_422_not_a_500():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)

        with pytest.raises(AppException) as exc:
            service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id=""))
        assert exc.value.status_code == 422


def test_an_empty_string_agent_id_on_create_is_422_not_a_500():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)

        with pytest.raises(AppException) as exc:
            service.create_customer(
                CustomerCreate(
                    customer_code=unique_code("C")[:50],
                    customer_name="Eta Traders",
                    sales_agent_id="",
                )
            )
        assert exc.value.status_code == 422


def test_clearing_the_agent_persists_null():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)
        agent = _agent(session)
        service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id=agent.id))

        cleared = service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id=None))
        assert cleared.sales_agent_id is None

        fetched = service.get_customer(str(customer.id))
        assert fetched.sales_agent_id is None
        assert fetched.sales_agent_code is None
        assert fetched.sales_agent_name is None


def test_the_list_endpoint_carries_the_agent_columns():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)
        agent = _agent(session)
        service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id=agent.id))

        result = service.list_customers(query=customer.customer_code)
        rows = result["data"]
        assert len(rows) == 1
        row = rows[0]
        assert str(row.sales_agent_id) == str(agent.id)
        assert row.sales_agent_code == agent.sales_agent
        assert row.sales_agent_name == agent.person_label


def test_create_customer_accepts_a_sales_agent():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        agent = _agent(session)

        customer = service.create_customer(
            CustomerCreate(
                customer_code=unique_code("C")[:50],
                customer_name="Epsilon Trading",
                sales_agent_id=agent.id,
            )
        )
        assert str(customer.sales_agent_id) == str(agent.id)


def test_create_customer_rejects_an_unknown_agent():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)

        with pytest.raises(AppException) as exc:
            service.create_customer(
                CustomerCreate(
                    customer_code=unique_code("C")[:50],
                    customer_name="Zeta Traders",
                    sales_agent_id=str(uuid.uuid4()),
                )
            )
        assert exc.value.status_code == 422


# ------------------------------------------------------------------------- inactive agents


def test_an_inactive_agent_is_rejected_on_a_genuine_change():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)
        inactive_agent = _agent(session, code="INACT", active=False)

        with pytest.raises(AppException) as exc:
            service.update_customer(
                str(customer.id), CustomerUpdate(sales_agent_id=inactive_agent.id)
            )
        assert exc.value.status_code == 422


def test_an_inactive_agent_is_rejected_on_create():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        inactive_agent = _agent(session, code="INACT2", active=False)

        with pytest.raises(AppException) as exc:
            service.create_customer(
                CustomerCreate(
                    customer_code=unique_code("C")[:50],
                    customer_name="Theta Traders",
                    sales_agent_id=inactive_agent.id,
                )
            )
        assert exc.value.status_code == 422


def test_resubmitting_the_same_already_inactive_agent_does_not_block_an_unrelated_edit():
    """A customer tied to an agent later deactivated must still be editable - the form
    resubmits the WHOLE payload on every save, so only a genuine re-pick of a different
    agent should have to be active (PR #1177 review, should-fix item 2)."""
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        agent = _agent(session, code="WASACTIVE")
        customer = service.create_customer(
            CustomerCreate(
                customer_code=unique_code("C")[:50],
                customer_name="Iota Traders",
                sales_agent_id=agent.id,
            )
        )
        agent.is_active = False
        session.flush()

        updated = service.update_customer(
            str(customer.id),
            CustomerUpdate(customer_name="Iota Traders Sdn Bhd", sales_agent_id=agent.id),
        )
        assert updated.customer_name == "Iota Traders Sdn Bhd"
        assert str(updated.sales_agent_id) == str(agent.id)


# --------------------------------------------------------------------------- company scope


def test_an_agent_from_another_company_is_rejected():
    with blank_session() as session:
        other_company_id = str(uuid.uuid4())
        session.add(Company(id=other_company_id, name="ZZT Other Co", code=unique_code("CO")[:50]))
        session.flush()

        set_company_scope(session, frozenset({other_company_id}))
        other_agent = _agent(session, company_id=other_company_id, code="OTH")

        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer = _customer(session, service)

        with pytest.raises(AppException) as exc:
            service.update_customer(
                str(customer.id), CustomerUpdate(sales_agent_id=other_agent.id)
            )
        assert exc.value.status_code == 422


def test_a_shared_agent_is_visible_to_any_company():
    """`company_id IS NULL` is the shape every one of today's ~38 real agents has."""
    with blank_session() as session:
        other_company_id = str(uuid.uuid4())
        session.add(Company(id=other_company_id, name="ZZT Shared Co", code=unique_code("CO")[:50]))
        session.flush()

        shared_agent = _agent(session, company_id=None, code="SHR")

        set_company_scope(session, frozenset({other_company_id}))
        service = CustomerService(session)
        customer = _customer(session, service)

        updated = service.update_customer(
            str(customer.id), CustomerUpdate(sales_agent_id=shared_agent.id)
        )
        assert str(updated.sales_agent_id) == str(shared_agent.id)


def test_a_user_scoped_to_two_companies_cannot_cross_link_a_b_owned_agent_onto_an_a_customer():
    """PR #1177 review, security item 3. The write-path check must compare the agent
    against the CUSTOMER's own company, not the caller's scope: a caller scoped to BOTH A
    and B must not be able to use that breadth to link a B-owned agent onto an A customer -
    the shape a caller-scope check alone would have let through.
    """
    with blank_session() as session:
        company_b = str(uuid.uuid4())
        session.add(Company(id=company_b, name="ZZT Company B", code=unique_code("CO")[:50]))
        session.flush()

        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        service = CustomerService(session)
        customer_a = _customer(session, service)  # company_id == DEFAULT_COMPANY_ID ("A")

        set_company_scope(session, frozenset({company_b}))
        agent_b = _agent(session, company_id=company_b, code="XCO")

        # The caller's own scope spans BOTH companies.
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID, company_b}))

        with pytest.raises(AppException) as exc:
            service.update_customer(
                str(customer_a.id), CustomerUpdate(sales_agent_id=agent_b.id)
            )
        assert exc.value.status_code == 422


# ----------------------------------------------------------------------- sales_agent_service


def test_scope_filter_returns_none_for_unrestricted_scope():
    assert sales_agent_service.scope_filter(None) is None


def test_scope_filter_excludes_other_companies_and_includes_shared_and_own():
    with blank_session() as session:
        other_company_id = str(uuid.uuid4())
        session.add(Company(id=other_company_id, name="ZZT SF Co", code=unique_code("CO")[:50]))
        session.flush()
        other_agent = _agent(session, company_id=other_company_id, code="SFOTH")
        shared_agent = _agent(session, company_id=None, code="SFSHR")
        mine_agent = _agent(session, company_id=DEFAULT_COMPANY_ID, code="SFMINE")

        predicate = sales_agent_service.scope_filter(frozenset({DEFAULT_COMPANY_ID}))
        ids = {
            a.id
            for a in session.query(SalesAgent).filter(predicate).all()
        }

        assert other_agent.id not in ids
        assert shared_agent.id in ids
        assert mine_agent.id in ids


def test_scope_filter_fails_closed_to_shared_only_when_empty():
    with blank_session() as session:
        shared_agent = _agent(session, company_id=None, code="SFSHR2")
        owned_agent = _agent(session, company_id=DEFAULT_COMPANY_ID, code="SFOWN2")

        predicate = sales_agent_service.scope_filter(frozenset())
        ids = {
            a.id
            for a in session.query(SalesAgent).filter(predicate).all()
        }

        assert shared_agent.id in ids
        assert owned_agent.id not in ids


# --------------------------------------------------------------------------------- routes
#
# Serializes through the REAL FastAPI route + `CustomerResponse` (not the ORM object the
# service hands back) - the gap the review's mutation M1 found: deleting the three fields
# from `CustomerResponse` still left all 8 prior tests green.


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _route_client(db, monkeypatch, *, scope, permitted: bool = True) -> TestClient:
    """A TestClient wired to `db` (the same session the test seeded), following the shape
    `tests/test_orders_so_outstanding.py`'s `client` fixture already uses."""
    principal = {"id": str(uuid.uuid4()), "email": "zzt-customer-agent@test.com"}

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: permitted,
    )
    return TestClient(app)


def test_the_get_route_serializes_sales_agent_id_code_and_name(db, monkeypatch):
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    service = CustomerService(db)
    customer = _customer(db, service)
    agent = _agent(db)
    service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id=agent.id))

    client = _route_client(db, monkeypatch, scope=frozenset({DEFAULT_COMPANY_ID}))
    resp = client.get(f"/api/v1/order-management/customers/{customer.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sales_agent_id"] == str(agent.id)
    assert body["sales_agent_code"] == agent.sales_agent
    assert body["sales_agent_name"] == agent.person_label


def test_the_list_route_serializes_sales_agent_id_code_and_name(db, monkeypatch):
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    service = CustomerService(db)
    customer = _customer(db, service)
    agent = _agent(db)
    service.update_customer(str(customer.id), CustomerUpdate(sales_agent_id=agent.id))

    client = _route_client(db, monkeypatch, scope=frozenset({DEFAULT_COMPANY_ID}))
    resp = client.get(
        "/api/v1/order-management/customers", params={"query": customer.customer_code}
    )

    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["sales_agent_id"] == str(agent.id)
    assert rows[0]["sales_agent_code"] == agent.sales_agent
    assert rows[0]["sales_agent_name"] == agent.person_label


def test_the_post_route_rejects_an_unknown_agent_with_422(db, monkeypatch):
    client = _route_client(db, monkeypatch, scope=frozenset({DEFAULT_COMPANY_ID}))

    resp = client.post(
        "/api/v1/order-management/customers/",
        json={
            "customer_code": unique_code("C")[:50],
            "customer_name": "Kappa Traders",
            "sales_agent_id": str(uuid.uuid4()),
        },
    )

    assert resp.status_code == 422, resp.text


def test_the_sales_agents_select_route_excludes_other_companies_and_includes_shared(
    db, monkeypatch
):
    other_company_id = str(uuid.uuid4())
    db.add(Company(id=other_company_id, name="ZZT Select Other Co", code=unique_code("CO")[:50]))
    db.flush()
    other_agent = _agent(db, company_id=other_company_id, code="SELOTH")
    shared_agent = _agent(db, company_id=None, code="SELSHR")

    client = _route_client(db, monkeypatch, scope=frozenset({DEFAULT_COMPANY_ID}))
    resp = client.get("/api/v1/order-management/customers/sales-agents-select")

    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["data"]}
    assert shared_agent.id in ids
    assert other_agent.id not in ids


def test_the_sales_agents_select_route_denies_without_the_permission(db, monkeypatch):
    client = _route_client(
        db, monkeypatch, scope=frozenset({DEFAULT_COMPANY_ID}), permitted=False
    )

    resp = client.get("/api/v1/order-management/customers/sales-agents-select")

    assert resp.status_code == 403
    assert "order_management.customers.view" in resp.text
