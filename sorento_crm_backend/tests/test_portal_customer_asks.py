"""Chatbot stock ask v2 S6 (PLAN-chatbot-stock-ask-v2-24sep.md "S6 - Portal Customer asks
page"): AC-SA601 to AC-SA604, and the BE half of AC-SA607 (the CRM and the portal work the
same row).

`GET /api/v1/public/portal/customer-asks` and `PATCH .../customer-asks/{ask_id}` at route
level, on the portal token: the scope is "asks of customers assigned to the sales agent this
portal contact is linked to", never the agent's 24-month order debtors.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.base import set_company_scope
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from app.models.stock_ask import StockAsk
from app.services import price_tag_request_service as ptr
from app.services import stock_ask_service

from ._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"
BASE = "/api/v1/public/portal/customer-asks"


def _uid() -> str:
    return str(uuid.uuid4())


def _contact(db, name: str) -> str:
    cid = _uid()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, name, session_vars) "
            "VALUES (:id, :rid, :phone, :name, CAST('{}' AS jsonb))"
        ),
        {"id": cid, "rid": f"ZZT-{_uid()[:8]}", "phone": f"+6005{uuid.uuid4().int % 10**7:07d}", "name": name},
    )
    return cid


def _agent(db, contact_id: str | None, code: str) -> SalesAgent:
    row = SalesAgent(id=_uid(), sales_agent=f"ZZT{code}{_uid()[:4]}", contact_id=contact_id, company_id=SORENTO)
    db.add(row)
    db.flush()
    return row


def _customer(db, name: str, agent: SalesAgent | None) -> Customer:
    row = Customer(
        id=_uid(),
        customer_code=f"ZZT-C-{_uid()[:6]}",
        customer_name=name,
        company_id=SORENTO,
        sales_agent_id=agent.id if agent else None,
    )
    db.add(row)
    db.flush()
    return row


def _ask(db, customer: Customer | None, contact_id: str, code: str, minutes_ago: int = 0) -> StockAsk:
    row = StockAsk(
        id=_uid(),
        company_id=SORENTO,
        customer_id=customer.id if customer else None,
        contact_id=contact_id,
        product_code=code,
        quantity=10,
        branch="no_incoming",
        answer_summary=f"{code} x 10: no stock and no incoming at the moment, please refer to your salesman.",
        notified_agent=True,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def world():
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        dealer = _contact(db, "Ah Seng")
        agent_contact = _contact(db, "Agent Lim")
        other_agent_contact = _contact(db, "Agent Tan")
        stranger = _contact(db, "Not An Agent")
        agent = _agent(db, agent_contact, "LIM")
        other_agent = _agent(db, other_agent_contact, "TAN")
        mine = _customer(db, "Hock Lee Trading", agent)
        mine2 = _customer(db, "Seng Heng Motor", agent)
        theirs = _customer(db, "Other Agent Trading", other_agent)
        world = {
            "db": db,
            "dealer": dealer,
            "agent_contact": agent_contact,
            "stranger": stranger,
            "agent": agent,
            "mine": mine,
            "old": _ask(db, mine, dealer, "SRT-OLD", minutes_ago=60),
            "new": _ask(db, mine2, dealer, "SRT-NEW", minutes_ago=1),
            "theirs": _ask(db, theirs, dealer, "SRT-THEIRS"),
            "orphan": _ask(db, None, dealer, "SRT-ORPHAN"),
        }
        db.commit()
        yield world


def _client(world, contact_id: str) -> TestClient:
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken
    from app.services.company_scope_resolver import apply_company_scope

    db = world["db"]

    def _override_get_db():
        yield db

    async def _override_scope():
        set_company_scope(db, frozenset({SORENTO}))
        return frozenset({SORENTO})

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    app.dependency_overrides[get_portal_token] = lambda: PortalToken(
        id=_uid(), contact_id=contact_id, space_id="zzt-space"
    )
    return TestClient(app, headers={"X-Portal-Token": "zzt-token"}, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# AC-SA601: one agent resolution
# --------------------------------------------------------------------------- #


def test_ac_sa601_sales_agent_for_contact_resolves_the_linked_agent(world):
    db = world["db"]
    assert ptr.sales_agent_for_contact(db, world["agent_contact"]).id == world["agent"].id
    assert ptr.sales_agent_for_contact(db, world["stranger"]) is None


def test_ac_sa601_two_links_answer_the_first_by_code_and_warn(world, caplog):
    db = world["db"]
    second = _agent(db, world["agent_contact"], "AAA")
    with caplog.at_level(logging.WARNING):
        picked = ptr.sales_agent_for_contact(db, world["agent_contact"])
    assert picked.id == second.id  # "ZZTAAA..." sorts before "ZZTLIM..."
    assert "linked to 2 sales agents" in caplog.text


def test_ac_sa601_the_debtor_lookup_goes_through_it(world, monkeypatch):
    db = world["db"]
    monkeypatch.setattr(ptr, "sales_agent_for_contact", lambda db_, contact_id: None)
    assert ptr.PriceTagRequestService.lookup_debtors_for_agent(db, world["agent_contact"]) == []


def test_ac_sa601_the_new_routes_go_through_it(world, monkeypatch):
    calls = []
    real = ptr.sales_agent_for_contact

    def spy(db_, contact_id):
        calls.append(contact_id)
        return real(db_, contact_id)

    monkeypatch.setattr(ptr, "sales_agent_for_contact", spy)
    resp = _client(world, world["agent_contact"]).get(BASE)
    assert resp.status_code == 200, resp.text
    assert calls == [world["agent_contact"]]


# --------------------------------------------------------------------------- #
# AC-SA602: the agent's own customers only
# --------------------------------------------------------------------------- #


def test_ac_sa602_lists_asks_of_the_agents_customers_newest_first(world):
    resp = _client(world, world["agent_contact"]).get(BASE)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["product_code"] for r in body["data"]] == ["SRT-NEW", "SRT-OLD"]
    assert body["pagination"]["total"] == 2
    assert body["data"][0]["customer_name"] == "Seng Heng Motor"
    assert body["data"][0]["contact_name"] == "Ah Seng"
    for key in ("customer_id", "contact_id", "product_id"):
        assert key not in body["data"][0]


def test_ac_sa602_paged_and_searchable(world):
    client = _client(world, world["agent_contact"])
    page2 = client.get(f"{BASE}?page=2&limit=1").json()
    assert [r["product_code"] for r in page2["data"]] == ["SRT-OLD"]
    by_customer = client.get(f"{BASE}?q=hock lee").json()
    assert [r["product_code"] for r in by_customer["data"]] == ["SRT-OLD"]
    by_product = client.get(f"{BASE}?q=srt-new").json()
    assert [r["product_code"] for r in by_product["data"]] == ["SRT-NEW"]


# --------------------------------------------------------------------------- #
# AC-SA603: a contact that is no sales agent
# --------------------------------------------------------------------------- #


def test_ac_sa603_a_non_agent_contact_is_403_on_get_and_patch(world):
    client = _client(world, world["stranger"])
    got = client.get(BASE)
    assert got.status_code == 403
    assert got.json().get("code") == "NOT_A_SALES_AGENT", got.text
    patched = client.patch(f"{BASE}/{world['old'].id}", json={"state": "done"})
    assert patched.status_code == 403
    assert patched.json().get("code") == "NOT_A_SALES_AGENT"


# --------------------------------------------------------------------------- #
# AC-SA604: PATCH
# --------------------------------------------------------------------------- #


def test_ac_sa604_patch_persists_state_and_note(world):
    client = _client(world, world["agent_contact"])
    resp = client.patch(f"{BASE}/{world['old'].id}", json={"state": "done", "note": "Visited, will order Friday"})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["state"], resp.json()["note"]) == ("done", "Visited, will order Friday")


def test_ac_sa604_an_out_of_scope_ask_is_404(world):
    client = _client(world, world["agent_contact"])
    assert client.patch(f"{BASE}/{world['theirs'].id}", json={"state": "done"}).status_code == 404
    assert client.patch(f"{BASE}/{world['orphan'].id}", json={"state": "done"}).status_code == 404


def test_ac_sa604_a_bad_state_is_422(world):
    client = _client(world, world["agent_contact"])
    assert client.patch(f"{BASE}/{world['old'].id}", json={"state": "closed"}).status_code == 422


# --------------------------------------------------------------------------- #
# AC-SA607 (BE half): the CRM and the portal share one row
# --------------------------------------------------------------------------- #


def test_ac_sa607_the_portal_edit_is_what_the_crm_tab_reads(world):
    client = _client(world, world["agent_contact"])
    client.patch(f"{BASE}/{world['old'].id}", json={"state": "done", "note": "Quoted 10"})
    db = world["db"]
    db.expire_all()
    crm = stock_ask_service.list_for_customer(db, world["mine"].id, page=1, limit=20)
    row = next(r for r in crm["data"] if r.id == world["old"].id)
    assert (row.state, row.note) == ("done", "Quoted 10")
    # ...and the other way round.
    stock_ask_service.update_for_customer(db, world["mine"].id, world["old"].id, {"state": "open"})
    listed = client.get(BASE).json()["data"]
    assert next(r for r in listed if r["id"] == world["old"].id)["state"] == "open"


def test_ac_sa606_the_open_filter_counts_only_open_asks(world):
    """The portal link reads the open count off `?state=open&limit=1`."""
    client = _client(world, world["agent_contact"])
    client.patch(f"{BASE}/{world['old'].id}", json={"state": "done"})
    body = client.get(f"{BASE}?state=open&limit=1").json()
    assert body["pagination"]["total"] == 1
    assert [r["product_code"] for r in body["data"]] == ["SRT-NEW"]
