"""Assign a sales agent to a customer (#1170 slice 1, small fix track).

`customers.sales_agent_id` already existed (read by the portal debtor dropdown), but nothing
on the CRM side could set it: `CustomerUpdate`/`CustomerCreate` did not carry the field and
`CustomerResponse` did not carry it either - the classic drop, since `response_model` silently
strips anything not declared on the schema even when the ORM row has it.

Company scope matters because `sales_agents` is deliberately NOT `CompanyScopedMixin` (a
shared master, see `app/models/sales_agent.py`) - a plain `db.get` by id would let a customer
in one company pick an agent minted only for another.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.schemas.order import CustomerCreate, CustomerUpdate
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.error_handler import AppException
from app.services.order_service import CustomerService

from ._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()


def _customer(session, service: CustomerService) -> Customer:
    return service.create_customer(
        CustomerCreate(customer_code=unique_code("C")[:50], customer_name="Delta Hardware")
    )


def _agent(session, *, company_id=None, code: str = "AGT") -> SalesAgent:
    agent = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=unique_code(code)[:50],
        person_label="Sean Tan",
        company_id=company_id,
    )
    session.add(agent)
    session.flush()
    return agent


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
