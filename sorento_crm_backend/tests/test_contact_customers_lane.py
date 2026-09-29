"""Lane CONTACT-CUSTOMERS, Phase 2 red tests (AC-20 .. AC-32).

UAC ``documentation/plans/sales/contact-customers-29sep-acceptance-criteria.md``,
PLAN ``documentation/plans/sales/PLAN-contact-customers-29sep.md`` (D1, D2).

Written BEFORE any implementation exists. Every test is expected to fail because a
route is missing (404), a registry key is unregistered, or
``contact_customer_service.agents_for_contact`` does not exist - never on a fixture.

Two traps a missing route sets for a 404 assertion, handled by ``_domain_404``: the
router answers ``{"detail": "Not Found"}`` for a path it does not know, so a bare
``status_code == 404`` would pass today for the wrong reason. A domain 404 is the
``AppException`` body instead.

Postgres only (``blank_session``); every row is seeded here, CI's database is empty.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import RespondContact, RespondContactCustomer
from app.models.base import set_company_scope
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.form_action_grace import WINDOW_REVERSIBLE
from app.services.user_service import UserPermissionService

from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
BOTH = frozenset({SORENTO, MOCHA_ID})

CONTACT_VIEW = "user_management.contacts.view"
CONTACT_EDIT = "user_management.contacts.edit"
AGENT_VIEW = "master_data.sales_agents.view"
AGENT_EDIT = "master_data.sales_agents.edit"
ALL_PERMS = {CONTACT_VIEW, CONTACT_EDIT, AGENT_VIEW, AGENT_EDIT}

CONTACTS = "/api/v1/user-management/contacts"
AGENTS = "/api/v1/master-data/sales-agents"
CUSTOMER_SELECT = "/api/v1/order-management/customers/select"


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        set_company_scope(session, BOTH)
        yield session


@pytest.fixture
def state(db):
    """Mutable per-test knobs the request overrides read on every call."""
    return {"scope": frozenset({SORENTO}), "granted": set(ALL_PERMS)}


@pytest.fixture
def actor(db):
    """A real users row: `linked_by` and `sla_form_actions.requested_by_id` are FKs."""
    from app.models.user import User

    row = User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@test.com", name="ZZT Actor")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def client(db, state, actor, monkeypatch):
    principal = {"id": actor.id, "email": actor.email}

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, state["scope"])
        return state["scope"]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in state["granted"],
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------- seeding


def _digits9() -> str:
    return str(uuid.uuid4().int % 10**8 + 10**8)  # nine digits, never a leading zero


def _contact(db, phone: str | None = None) -> RespondContact:
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone or f"60{_digits9()}",
        name=f"ZZT contact {unique_code('c')}",
    )
    db.add(row)
    db.flush()
    return row


def _agent(db, *, code: str | None = None, company_id=None, is_active=True, person_label=None) -> SalesAgent:
    row = SalesAgent(
        id=str(uuid.uuid4()),
        sales_agent=code or unique_code("AGT"),
        source="manual",
        is_active=is_active,
        company_id=company_id,
        person_label=person_label,
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, *, company_id=SORENTO, agent=None, **overrides) -> Customer:
    code = overrides.pop("customer_code", None) or unique_code("ZZTC")
    fields = dict(
        customer_code=code,
        customer_name=overrides.pop("customer_name", f"ZZT customer {code}"),
        company_id=company_id,
        sales_agent_id=agent.id if agent else None,
    )
    fields.update(overrides)
    row = Customer(**fields)
    db.add(row)
    db.flush()
    return row


def _link(db, contact, customer, *, is_primary=False, age_minutes=0) -> RespondContactCustomer:
    row = RespondContactCustomer(
        contact_id=contact.id,
        customer_id=customer.id,
        company_id=customer.company_id,
        is_primary=is_primary,
        source="manual",
        created_at=datetime(2026, 1, 1) + timedelta(minutes=age_minutes),
    )
    db.add(row)
    db.flush()
    return row


def _links_in_db(db, contact_id) -> list[RespondContactCustomer]:
    set_company_scope(db, BOTH)
    db.expire_all()
    return (
        db.query(RespondContactCustomer)
        .filter(RespondContactCustomer.contact_id == contact_id)
        .order_by(RespondContactCustomer.created_at)
        .all()
    )


def _domain_404(response) -> bool:
    """A 404 raised by the handler, not FastAPI's 'no such route'."""
    return response.status_code == 404 and response.json() != {"detail": "Not Found"}


# ------------------------------------------------- pending-action park + commit


def _park(client, *, action_key, entity_type, entity_id, payload=None):
    return client.post(
        "/api/v1/pending-actions",
        json={
            "action_key": action_key,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "payload": payload or {},
        },
    )


def _lapse(db, action_id: str) -> None:
    from app.models.sla import SlaFormAction

    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def _commit(client, db, *, entity_type, entity_id, action_id):
    """Lapse the window; the lazy commit on GET applies it, as a poll would."""
    _lapse(db, action_id)
    return client.get(
        "/api/v1/pending-actions/current",
        params={"entity_type": entity_type, "entity_id": str(entity_id)},
    )


# ============================================================ AC-20 list links


def test_ac20_get_contact_customers_lists_links_in_created_order(client, db):
    contact = _contact(db)
    agent_a = _agent(db, person_label="ZZT Alice")
    agent_b = _agent(db)
    first = _customer(db, agent=agent_a)
    second = _customer(db, agent=agent_b)
    # Insert the later link first so ordering by created_at, not by insertion, is proven.
    link_second = _link(db, contact, second, is_primary=True, age_minutes=10)
    link_first = _link(db, contact, first, age_minutes=1)
    db.commit()

    response = client.get(f"{CONTACTS}/{contact.id}/customers")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["customer_id"] for row in body["data"]] == [first.id, second.id]
    row = body["data"][0]
    # `id` is the respond_contact_customers row id, what the unlink action parks on.
    assert [r["id"] for r in body["data"]] == [link_first.id, link_second.id]
    assert row["customer_code"] == first.customer_code
    assert row["customer_name"] == first.customer_name
    assert row["is_active"] is True
    assert row["is_primary"] is False
    assert row["source"] == "manual"
    assert row["sales_agent_id"] == agent_a.id
    assert row["sales_agent_code"] == agent_a.sales_agent
    assert row["sales_agent_name"] == "ZZT Alice"
    assert row["created_at"]
    assert body["data"][1]["is_primary"] is True
    assert body["data"][1]["sales_agent_code"] == agent_b.sales_agent


def test_ac20_unlinked_contact_returns_empty_data(client, db):
    contact = _contact(db)
    db.commit()

    response = client.get(f"{CONTACTS}/{contact.id}/customers")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


# ============================================================ AC-21 suggestions


def test_ac21_suggested_lists_unlinked_phone_matches_only(client, db):
    digits = _digits9()
    contact = _contact(db, phone=f"60{digits}")
    agent = _agent(db, person_label="ZZT Bob")
    match = _customer(db, agent=agent, phone_number=f"0{digits}")
    linked = _customer(db, phone_number=f"+60 {digits}")
    other = _customer(db, phone_number="60999999999")
    _link(db, contact, linked)
    db.commit()

    response = client.get(f"{CONTACTS}/{contact.id}/customers")

    assert response.status_code == 200, response.text
    suggested = response.json()["suggested"]
    assert [row["customer_id"] for row in suggested] == [match.id]
    row = suggested[0]
    assert row["customer_code"] == match.customer_code
    assert row["customer_name"] == match.customer_name
    assert row["phone_number"] == f"0{digits}"
    assert row["sales_agent_code"] == agent.sales_agent
    assert row["sales_agent_name"] == "ZZT Bob"
    assert other.id not in [r["customer_id"] for r in suggested]
    assert linked.id not in [r["customer_id"] for r in suggested]


def test_ac21_suggested_is_capped_at_five(client, db):
    digits = _digits9()
    contact = _contact(db, phone=f"60{digits}")
    for _ in range(7):
        _customer(db, phone_number=f"0{digits}")
    db.commit()

    response = client.get(f"{CONTACTS}/{contact.id}/customers")

    assert response.status_code == 200, response.text
    assert len(response.json()["suggested"]) == 5


def test_ac21_no_phone_match_returns_empty_suggested(client, db):
    contact = _contact(db, phone="60111111111")
    _customer(db, phone_number="60999999999")
    db.commit()

    response = client.get(f"{CONTACTS}/{contact.id}/customers")

    assert response.status_code == 200, response.text
    assert response.json()["suggested"] == []


# ============================================================ AC-22 link


def test_ac22_post_link_stamps_customer_company_and_is_idempotent(client, db, actor):
    contact = _contact(db)
    customer = _customer(db)
    db.commit()

    first = client.post(f"{CONTACTS}/{contact.id}/customers", json={"customer_id": customer.id})

    assert first.status_code == 201, first.text
    assert first.json()["customer_id"] == customer.id
    assert first.json()["id"] == _links_in_db(db, contact.id)[0].id
    assert first.json()["customer_code"] == customer.customer_code
    links = _links_in_db(db, contact.id)
    assert len(links) == 1
    assert links[0].company_id == SORENTO
    assert links[0].source == "manual"
    assert links[0].linked_by == actor.id
    link_id = links[0].id

    again = client.post(f"{CONTACTS}/{contact.id}/customers", json={"customer_id": customer.id})

    assert again.status_code == 201, again.text
    assert again.json() == first.json()
    links = _links_in_db(db, contact.id)
    assert len(links) == 1
    assert links[0].id == link_id


def test_ac22_post_link_under_two_company_scope_takes_the_customers_company(client, db, state):
    state["scope"] = BOTH
    contact = _contact(db)
    customer = _customer(db, company_id=MOCHA_ID)
    db.commit()

    response = client.post(f"{CONTACTS}/{contact.id}/customers", json={"customer_id": customer.id})

    assert response.status_code == 201, response.text
    links = _links_in_db(db, contact.id)
    assert len(links) == 1
    assert links[0].company_id == MOCHA_ID


# ============================================================ AC-23 link refusals


def test_ac23_unknown_customer_is_404(client, db):
    contact = _contact(db)
    db.commit()

    response = client.post(
        f"{CONTACTS}/{contact.id}/customers", json={"customer_id": str(uuid.uuid4())}
    )

    assert _domain_404(response), response.text


def test_ac23_customer_outside_scope_is_404(client, db, state):
    contact = _contact(db)
    foreign = _customer(db, company_id=MOCHA_ID)
    db.commit()
    state["scope"] = frozenset({SORENTO})

    response = client.post(f"{CONTACTS}/{contact.id}/customers", json={"customer_id": foreign.id})

    assert _domain_404(response), response.text
    assert _links_in_db(db, contact.id) == []


def test_ac23_unknown_contact_is_404(client, db):
    customer = _customer(db)
    db.commit()

    response = client.post(
        f"{CONTACTS}/{uuid.uuid4()}/customers", json={"customer_id": customer.id}
    )

    assert _domain_404(response), response.text


def test_ac23_post_is_primary_demotes_the_other_primary(client, db):
    contact = _contact(db)
    first = _customer(db)
    second = _customer(db)
    db.commit()

    r1 = client.post(
        f"{CONTACTS}/{contact.id}/customers", json={"customer_id": first.id, "is_primary": True}
    )
    r2 = client.post(
        f"{CONTACTS}/{contact.id}/customers", json={"customer_id": second.id, "is_primary": True}
    )

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r2.json()["is_primary"] is True
    primaries = {link.customer_id for link in _links_in_db(db, contact.id) if link.is_primary}
    assert primaries == {second.id}


# ============================================================ AC-24 patch primary


def test_ac24_patch_true_demotes_other_primary_and_false_clears(client, db):
    contact = _contact(db)
    first = _customer(db)
    second = _customer(db)
    _link(db, contact, first, is_primary=True, age_minutes=1)
    link_second = _link(db, contact, second, age_minutes=2)
    db.commit()
    link_second_id = link_second.id

    promote = client.patch(
        f"{CONTACTS}/{contact.id}/customers/{second.id}", json={"is_primary": True}
    )

    assert promote.status_code == 200, promote.text
    assert promote.json()["customer_id"] == second.id
    assert promote.json()["id"] == link_second_id
    assert promote.json()["is_primary"] is True
    assert {l.customer_id for l in _links_in_db(db, contact.id) if l.is_primary} == {second.id}

    clear = client.patch(
        f"{CONTACTS}/{contact.id}/customers/{second.id}", json={"is_primary": False}
    )

    assert clear.status_code == 200, clear.text
    assert clear.json()["is_primary"] is False
    assert clear.json()["id"] == link_second_id
    assert [l for l in _links_in_db(db, contact.id) if l.is_primary] == []


def test_ac24_patch_unlinked_pair_is_404(client, db):
    contact = _contact(db)
    customer = _customer(db)
    db.commit()

    response = client.patch(
        f"{CONTACTS}/{contact.id}/customers/{customer.id}", json={"is_primary": True}
    )

    assert _domain_404(response), response.text


# ============================================================ AC-25 unlink action


def test_ac25_unlink_action_is_registered_reversible_and_gated():
    from app.services.form_action_registry import get_action

    action = get_action("contact_customer_link.unlink")

    assert action is not None, "contact_customer_link.unlink is not registered"
    assert action.window == WINDOW_REVERSIBLE
    assert action.permission == CONTACT_EDIT
    assert "contact_customer_link" in action.entity_types


def test_ac25_unlink_action_deletes_the_link_and_keeps_both_ends(client, db):
    contact = _contact(db)
    customer = _customer(db)
    link = _link(db, contact, customer)
    db.commit()
    link_id, contact_id, customer_id = link.id, contact.id, customer.id

    parked = _park(
        client,
        action_key="contact_customer_link.unlink",
        entity_type="contact_customer_link",
        entity_id=link_id,
    )
    assert parked.status_code == 202, parked.text
    committed = _commit(
        client,
        db,
        entity_type="contact_customer_link",
        entity_id=link_id,
        action_id=parked.json()["id"],
    )

    assert committed.json()["last_outcome"]["status"] == "committed", committed.json()
    assert _links_in_db(db, contact_id) == []
    assert db.query(RespondContact).filter(RespondContact.id == contact_id).first() is not None
    assert db.query(Customer).filter(Customer.id == customer_id).first() is not None


# ============================================================ AC-26 permissions


def test_ac26_get_without_contacts_view_is_403(client, db, state):
    contact = _contact(db)
    db.commit()
    state["granted"] = {CONTACT_EDIT}

    response = client.get(f"{CONTACTS}/{contact.id}/customers")

    assert response.status_code == 403, response.text


def test_ac26_post_and_patch_without_contacts_edit_are_403(client, db, state):
    contact = _contact(db)
    customer = _customer(db)
    _link(db, contact, customer)
    db.commit()
    state["granted"] = {CONTACT_VIEW}

    posted = client.post(f"{CONTACTS}/{contact.id}/customers", json={"customer_id": customer.id})
    patched = client.patch(
        f"{CONTACTS}/{contact.id}/customers/{customer.id}", json={"is_primary": True}
    )

    assert posted.status_code == 403, posted.text
    assert patched.status_code == 403, patched.text


# ============================================================ AC-27 agents_for_contact


def test_ac27_agents_for_contact_distinct_ordered_by_code(db):
    from app.services import contact_customer_service

    contact = _contact(db)
    agent_a = _agent(db, code=unique_code("A"))
    agent_b = _agent(db, code=unique_code("B"))
    # Two customers on A (must collapse to one), one on B, one with no agent at all.
    for customer in (
        _customer(db, agent=agent_b),
        _customer(db, agent=agent_a),
        _customer(db, agent=agent_a),
        _customer(db),
    ):
        _link(db, contact, customer)
    db.flush()

    agents = contact_customer_service.agents_for_contact(db, contact.id)

    assert [a.id for a in agents] == [agent_a.id, agent_b.id]


def test_ac27_agents_for_contact_without_links_is_empty(db):
    from app.services import contact_customer_service

    contact = _contact(db)
    no_agent = _customer(db)
    other = _contact(db)
    _link(db, other, no_agent)
    db.flush()

    assert contact_customer_service.agents_for_contact(db, contact.id) == []
    assert contact_customer_service.agents_for_contact(db, other.id) == []


# ============================================================ AC-28 agent's customers


def test_ac28_agent_customers_are_this_agents_only_sorted_by_code(client, db):
    tag = uuid.uuid4().hex[:6]
    agent = _agent(db)
    other_agent = _agent(db)
    # Inserted out of order: default sort is customer_code asc.
    from app.models.access import MarketSegment

    segment = MarketSegment(
        id=str(uuid.uuid4()), code=f"zzt-{tag}", name="ZZT segment", is_active=True
    )
    db.add(segment)
    db.flush()
    c3 = _customer(db, agent=agent, customer_code=f"ZZT-{tag}-C3")
    c1 = _customer(
        db,
        agent=agent,
        customer_code=f"ZZT-{tag}-C1",
        region="Selangor",
        market_segment_code=segment.code,
    )
    c2 = _customer(db, agent=agent, customer_code=f"ZZT-{tag}-C2")
    _customer(db, agent=other_agent, customer_code=f"ZZT-{tag}-C0")
    _customer(db, customer_code=f"ZZT-{tag}-C9")
    db.commit()

    response = client.get(f"{AGENTS}/{agent.id}/customers")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["data"]] == [c1.id, c2.id, c3.id]
    assert body["pagination"]["total"] == 3
    assert body["data"][0]["sales_agent_code"] == agent.sales_agent
    # Declared on CustomerResponse: response_model would silently drop them otherwise.
    assert body["data"][0]["region"] == "Selangor"
    assert body["data"][0]["market_segment_code"] == segment.code
    assert "region" in body["data"][1] and body["data"][1]["region"] is None


def test_ac28_agent_customers_query_matches_code_or_name(client, db):
    tag = uuid.uuid4().hex[:6]
    agent = _agent(db)
    by_code = _customer(db, agent=agent, customer_code=f"ZZT-{tag}-NEEDLE", customer_name="ZZT plain one")
    by_name = _customer(db, agent=agent, customer_code=f"ZZT-{tag}-B", customer_name="ZZT has needle inside")
    _customer(db, agent=agent, customer_code=f"ZZT-{tag}-C", customer_name="ZZT unrelated")
    db.commit()

    response = client.get(f"{AGENTS}/{agent.id}/customers", params={"query": "NEEDLE"})

    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["data"]} == {by_code.id, by_name.id}


def test_ac28_agent_customers_are_paged(client, db):
    tag = uuid.uuid4().hex[:6]
    agent = _agent(db)
    rows = [_customer(db, agent=agent, customer_code=f"ZZT-{tag}-P{i}") for i in range(3)]
    db.commit()

    page2 = client.get(f"{AGENTS}/{agent.id}/customers", params={"page": 2, "limit": 2})

    assert page2.status_code == 200, page2.text
    body = page2.json()
    assert [row["id"] for row in body["data"]] == [rows[2].id]
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["limit"] == 2


def test_ac28_agent_with_no_customers_gets_an_empty_page(client, db):
    agent = _agent(db)
    db.commit()

    response = client.get(f"{AGENTS}/{agent.id}/customers")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


# ============================================================ AC-29 assign


def test_ac29_assign_sets_the_agent_and_answers_the_customer(client, db):
    agent = _agent(db)
    customer = _customer(db)
    db.commit()

    response = client.post(f"{AGENTS}/{agent.id}/customers", json={"customer_id": customer.id})

    assert response.status_code == 200, response.text
    assert response.json()["id"] == customer.id
    assert response.json()["sales_agent_code"] == agent.sales_agent
    db.expire_all()
    assert db.get(Customer, customer.id).sales_agent_id == agent.id


def test_ac29_assign_moves_a_customer_from_another_agent(client, db):
    old_agent = _agent(db)
    agent = _agent(db)
    customer = _customer(db, agent=old_agent)
    db.commit()

    response = client.post(f"{AGENTS}/{agent.id}/customers", json={"customer_id": customer.id})

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Customer, customer.id).sales_agent_id == agent.id


def test_ac29_assign_to_an_inactive_agent_is_422(client, db):
    agent = _agent(db, is_active=False)
    customer = _customer(db)
    db.commit()

    response = client.post(f"{AGENTS}/{agent.id}/customers", json={"customer_id": customer.id})

    assert response.status_code == 422, response.text
    db.expire_all()
    assert db.get(Customer, customer.id).sales_agent_id is None


def test_ac29_assign_across_companies_is_422_but_shared_agent_is_allowed(client, db):
    owned_by_mocha = _agent(db, company_id=MOCHA_ID)
    shared = _agent(db)
    customer = _customer(db, company_id=SORENTO)
    db.commit()

    refused = client.post(
        f"{AGENTS}/{owned_by_mocha.id}/customers", json={"customer_id": customer.id}
    )
    allowed = client.post(f"{AGENTS}/{shared.id}/customers", json={"customer_id": customer.id})

    assert refused.status_code == 422, refused.text
    assert allowed.status_code == 200, allowed.text


def test_ac29_assign_unknown_customer_is_404(client, db):
    agent = _agent(db)
    db.commit()

    response = client.post(
        f"{AGENTS}/{agent.id}/customers", json={"customer_id": str(uuid.uuid4())}
    )

    assert _domain_404(response), response.text


# ============================================================ AC-30 unassign action


def test_ac30_unassign_action_is_registered_reversible_and_gated():
    from app.services.form_action_registry import get_action

    action = get_action("customer.unassign_sales_agent")

    assert action is not None, "customer.unassign_sales_agent is not registered"
    assert action.window == WINDOW_REVERSIBLE
    assert action.permission == AGENT_EDIT
    assert "customer" in action.entity_types


def test_ac30_unassign_clears_the_fk_when_it_still_matches(client, db):
    agent = _agent(db)
    customer = _customer(db, agent=agent)
    db.commit()

    parked = _park(
        client,
        action_key="customer.unassign_sales_agent",
        entity_type="customer",
        entity_id=customer.id,
        payload={"sales_agent_id": agent.id},
    )
    assert parked.status_code == 202, parked.text
    committed = _commit(
        client, db, entity_type="customer", entity_id=customer.id, action_id=parked.json()["id"]
    )

    assert committed.json()["last_outcome"]["status"] == "committed", committed.json()
    db.expire_all()
    assert db.get(Customer, customer.id).sales_agent_id is None


def test_ac30_unassign_leaves_a_customer_moved_to_another_agent(client, db):
    agent = _agent(db)
    other = _agent(db)
    customer = _customer(db, agent=agent)
    db.commit()

    parked = _park(
        client,
        action_key="customer.unassign_sales_agent",
        entity_type="customer",
        entity_id=customer.id,
        payload={"sales_agent_id": agent.id},
    )
    assert parked.status_code == 202, parked.text
    # Moved during the window.
    db.get(Customer, customer.id).sales_agent_id = other.id
    db.commit()
    committed = _commit(
        client, db, entity_type="customer", entity_id=customer.id, action_id=parked.json()["id"]
    )

    assert committed.json()["last_outcome"]["status"] == "committed", committed.json()
    db.expire_all()
    assert db.get(Customer, customer.id).sales_agent_id == other.id


# ============================================================ AC-31 customers select


def test_ac31_customers_select_carries_the_sales_agent(client, db):
    tag = uuid.uuid4().hex[:6]
    agent = _agent(db, person_label="ZZT Carol")
    handled = _customer(db, agent=agent, customer_code=f"ZZT-{tag}-H")
    free = _customer(db, customer_code=f"ZZT-{tag}-F")
    db.commit()

    response = client.get(CUSTOMER_SELECT, params={"query": f"ZZT-{tag}"})

    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["data"]}
    assert rows[handled.id]["sales_agent_id"] == agent.id
    assert rows[handled.id]["sales_agent_code"] == agent.sales_agent
    assert rows[handled.id]["sales_agent_name"] == "ZZT Carol"
    # Present and null, not absent: response shape is the contract.
    for key in ("sales_agent_id", "sales_agent_code", "sales_agent_name"):
        assert key in rows[free.id], key
        assert rows[free.id][key] is None
    # The existing fields stay.
    assert rows[handled.id]["customer_code"] == handled.customer_code
    assert rows[handled.id]["customer_name"] == handled.customer_name


# ============================================================ AC-32 audit


def test_ac32_assign_then_unassign_are_audited_with_the_sales_agent_change(client, db):
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    agent = _agent(db)
    customer = _customer(db)
    db.commit()
    customer_id = customer.id

    assigned = client.post(f"{AGENTS}/{agent.id}/customers", json={"customer_id": customer_id})
    assert assigned.status_code == 200, assigned.text

    parked = _park(
        client,
        action_key="customer.unassign_sales_agent",
        entity_type="customer",
        entity_id=customer_id,
        payload={"sales_agent_id": agent.id},
    )
    assert parked.status_code == 202, parked.text
    committed = _commit(
        client, db, entity_type="customer", entity_id=customer_id, action_id=parked.json()["id"]
    )
    assert committed.json()["last_outcome"]["status"] == "committed", committed.json()

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "customer", AuditLog.entity_id == str(customer_id))
        .order_by(AuditLog.changed_at)
        .all()
    )
    changes = [
        (row.new_values or {}).get("sales_agent_id")
        for row in rows
        if "sales_agent_id" in (row.new_values or {})
    ]
    # Assign wrote the agent id, unassign wrote null: the move is traceable.
    assert changes == [agent.id, None], [(r.action, r.new_values) for r in rows]
