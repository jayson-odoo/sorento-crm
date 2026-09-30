"""Portal Conversation view (lane SALES-CONVO, PLAN-sales-conversation-view-30sep.md).

`GET /api/v1/public/portal/conversations` and the thread reads under it, on the portal token:
the WhatsApp conversations of the customers assigned to the sales agent this portal contact is
linked to. UAC: `sales-conversation-view-30sep-acceptance-criteria.md` (AC-CV1 to AC-CV17).

Scope chain: portal contact -> `sales_agents.contact_id` -> `customers.sales_agent_id` ->
`respond_contact_customers` -> `respond_contacts.respond_io_id` -> `chat_histories.contact_id`.

Run:
    SORENTO_ENV_FILE=.env.ci-tests venv/bin/pytest tests/test_portal_conversations.py -q
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.access import RespondContactCustomer
from app.models.base import set_company_scope
from app.models.chat_history import ChatHistory
from app.models.order import Customer
from app.models.price_tag import ContactPortalFormOverride
from app.models.sales_agent import SalesAgent
from app.models.ticket_comment import ConversationTicketComment

from ._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"
MOCHA = "00000000-0000-0000-0000-000000000002"
BASE = "/api/v1/public/portal/conversations"
CONVERSATION = "conversation"

BASE_TIME = datetime(2026, 9, 29, 3, 0, 0)


def _uid() -> str:
    return str(uuid.uuid4())


class _DeadRespondClient:
    """Respond unreachable: the thread reads answer from the local lane, so the assertions
    stay about scope and shape, not about the network."""

    def list_messages(self, *a, **k):
        raise RuntimeError("Respond.io unreachable in tests")


@pytest.fixture(autouse=True)
def _local_lane_only():
    with patch("app.services.integration_service.RespondClient") as client_cls:
        client_cls.return_value = _DeadRespondClient()
        client_cls.for_identifier.return_value = _DeadRespondClient()
        client_cls.for_contact_id.return_value = _DeadRespondClient()
        yield client_cls


def _contact(db, name: str, *, respond_io_id: str | None = "auto", phone: str | None = None) -> str:
    cid = _uid()
    rid = f"ZZT-{_uid()[:8]}" if respond_io_id == "auto" else respond_io_id
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, name, session_vars) "
            "VALUES (:id, :rid, :phone, :name, CAST('{}' AS jsonb))"
        ),
        {
            "id": cid,
            "rid": rid,
            "phone": phone or f"+6005{uuid.uuid4().int % 10**7:07d}",
            "name": name,
        },
    )
    return cid


def _respond_io_id(db, contact_id: str) -> str | None:
    return db.execute(
        text("SELECT respond_io_id FROM respond_contacts WHERE id = :id"), {"id": contact_id}
    ).scalar()


def _phone(db, contact_id: str) -> str:
    return db.execute(
        text("SELECT phone_number FROM respond_contacts WHERE id = :id"), {"id": contact_id}
    ).scalar()


def _agent(db, contact_id: str | None, code: str) -> SalesAgent:
    row = SalesAgent(id=_uid(), sales_agent=f"ZZT{code}{_uid()[:4]}", contact_id=contact_id, company_id=SORENTO)
    db.add(row)
    db.flush()
    return row


def _switch(db, contact_id: str, on: bool, form_type: str = CONVERSATION) -> None:
    db.add(ContactPortalFormOverride(contact_id=contact_id, form_type=form_type, is_enabled=on))
    db.flush()


def _customer(db, name: str, agent: SalesAgent | None, company_id: str = SORENTO) -> Customer:
    row = Customer(
        id=_uid(),
        customer_code=f"ZZT-C-{_uid()[:6]}",
        customer_name=name,
        company_id=company_id,
        sales_agent_id=agent.id if agent else None,
    )
    db.add(row)
    db.flush()
    return row


def _link(db, contact_id: str, customer: Customer, *, primary: bool = False, company_id: str = SORENTO) -> None:
    db.add(
        RespondContactCustomer(
            id=_uid(), contact_id=contact_id, customer_id=customer.id, is_primary=primary, company_id=company_id
        )
    )
    db.flush()


def _message(db, contact_id: str, body: str, *, minutes: int, direction: str = "incoming", message_id: str | None = None) -> str:
    """One `chat_histories` row for the contact, `minutes` after BASE_TIME."""
    rid = _respond_io_id(db, contact_id)
    mid = message_id or str(1_700_000_000_000 + minutes)
    db.add(
        ChatHistory(
            channel="whatsapp",
            contact_id=rid,
            phone_number=_phone(db, contact_id),
            message=body,
            sent_at=BASE_TIME + timedelta(minutes=minutes),
            type=direction,
            message_id=mid,
        )
    )
    db.flush()
    return mid


@pytest.fixture
def world():
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        schema = db.get_bind()._execution_options["schema_translate_map"][None]
        db.execute(text(f'SET LOCAL search_path TO "{schema}"'))

        from app.models.company import Company

        if db.query(Company).filter(Company.id == MOCHA).first() is None:
            db.add(Company(id=MOCHA, name="Mocha", code=f"ZM{_uid()[:6]}", is_active=True))
            db.flush()

        agent_contact = _contact(db, "Agent Lim")
        other_agent_contact = _contact(db, "Agent Tan")
        stranger = _contact(db, "Not An Agent")
        switched_off_agent_contact = _contact(db, "Agent Wong")
        agent = _agent(db, agent_contact, "LIM")
        other_agent = _agent(db, other_agent_contact, "TAN")
        _agent(db, switched_off_agent_contact, "WONG")
        _switch(db, agent_contact, True)
        _switch(db, stranger, True)

        mine = _customer(db, "Chin Chun Hardware", agent)
        mine2 = _customer(db, "Lim Tiles Sdn Bhd", agent)
        mine3 = _customer(db, "Tan Home Living", agent)
        quiet = _customer(db, "Quiet Customer", agent)
        theirs = _customer(db, "Other Agent Trading", other_agent)

        chin = _contact(db, "Mr. Chin", phone="+60123456789")
        lim = _contact(db, "Ms. Lim")
        tan = _contact(db, "Mr. Tan")
        no_chat = _contact(db, "Never Wrote")
        no_respond = _contact(db, "No Respond Link", respond_io_id=None)
        rival = _contact(db, "Rival Dealer")
        mocha_only = _contact(db, "Mocha Dealer")

        _link(db, chin, mine, primary=True)
        _link(db, lim, mine2)
        # One person for two of my accounts: one row, the primary account named.
        _link(db, tan, mine3, primary=True)
        _link(db, tan, mine2)
        _link(db, no_chat, quiet)
        _link(db, no_respond, quiet)
        _link(db, rival, theirs)
        # A link in ANOTHER company to one of my customers never counts (company scope).
        _link(db, mocha_only, mine, company_id=MOCHA)

        _message(db, chin, "Hi, 60x60 grey matt tile still have?", minutes=0)
        _message(db, chin, "SR-6060-GM: 32 boxes in stock at Sorento.", minutes=1, direction="outgoing")
        _message(db, chin, "Boss, the 60x60 grey tile got stock or not?", minutes=90)
        _message(db, lim, "ok noted, I will confirm with my client tomorrow", minutes=60)
        _message(db, tan, "Your price tag request PT-202609-0031 is ready.", minutes=30, direction="outgoing")
        _message(db, rival, "hello from the other side", minutes=120)
        _message(db, mocha_only, "mocha hello", minutes=200)

        db.commit()
        yield {
            "db": db,
            "agent_contact": agent_contact,
            "stranger": stranger,
            "switched_off_agent_contact": switched_off_agent_contact,
            "agent": agent,
            "chin": chin,
            "lim": lim,
            "tan": tan,
            "no_chat": no_chat,
            "no_respond": no_respond,
            "rival": rival,
            "mocha_only": mocha_only,
            "mine": mine,
        }


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
# AC-CV1 / AC-CV17: one more grantable kind, off by default, agents only
# --------------------------------------------------------------------------- #


def test_ac_cv1_conversation_is_a_grantable_form_kind_default_off():
    from app.services.portal_service import GRANTABLE_PORTAL_FORM_TYPES, SUPPORTED_TYPES

    assert CONVERSATION in GRANTABLE_PORTAL_FORM_TYPES
    assert CONVERSATION not in SUPPORTED_TYPES
    # After Customer asks: the picker's order is the grantable order.
    assert GRANTABLE_PORTAL_FORM_TYPES[-2:] == ("customer_asks", CONVERSATION)


def test_ac_cv1_visible_form_types_needs_the_switch_and_a_linked_agent(world):
    from app.services.portal_form_visibility_service import resolve_visible_form_types

    db = world["db"]
    assert CONVERSATION in resolve_visible_form_types(db, world["agent_contact"])
    assert CONVERSATION not in resolve_visible_form_types(db, world["switched_off_agent_contact"])
    assert CONVERSATION not in resolve_visible_form_types(db, world["stranger"])
    assert CONVERSATION not in resolve_visible_form_types(db, world["chin"])


def test_ac_cv17_the_crm_contact_portal_forms_row_lists_it_off_by_default(world):
    from app.api.v1.user_management.contact_portal_forms import _build_view

    db = world["db"]
    off = {f["form_type"]: f for f in _build_view(db, world["switched_off_agent_contact"])["forms"]}
    assert off[CONVERSATION] == {
        "form_type": CONVERSATION, "inherited": False, "override": None, "effective": False,
    }
    on = {f["form_type"]: f for f in _build_view(db, world["agent_contact"])["forms"]}
    assert on[CONVERSATION]["effective"] is True


def test_ac_cv17_the_label_is_conversation():
    from app.services.portal_form_visibility_service import _label_for

    assert _label_for(CONVERSATION) == "Conversation"


# --------------------------------------------------------------------------- #
# AC-CV2 / AC-CV3: the two 403s, on every route
# --------------------------------------------------------------------------- #


def _every_route(world):
    chin = world["chin"]
    return (
        BASE,
        f"{BASE}/{chin}/page",
        f"{BASE}/{chin}/search?q=tile",
        f"{BASE}/{chin}/comments",
    )


def test_ac_cv3_a_non_agent_contact_is_403_everywhere(world):
    client = _client(world, world["stranger"])
    for path in _every_route(world):
        got = client.get(path)
        assert got.status_code == 403, (path, got.text)
        assert got.json().get("code") == "NOT_A_SALES_AGENT", (path, got.text)


def test_ac_cv2_a_linked_agent_with_the_switch_off_is_403_everywhere(world):
    client = _client(world, world["switched_off_agent_contact"])
    for path in _every_route(world):
        got = client.get(path)
        assert got.status_code == 403, (path, got.text)
        assert got.json().get("code") == "FORM_TYPE_NOT_VISIBLE", (path, got.text)


def test_ac_cv2_the_customer_asks_switch_does_not_open_this_kind(world):
    """Two switches, two kinds: Customer asks on and Conversation off is still 403 here."""
    db = world["db"]
    _switch(db, world["switched_off_agent_contact"], True, form_type="customer_asks")
    got = _client(world, world["switched_off_agent_contact"]).get(BASE)
    assert got.status_code == 403
    assert got.json().get("code") == "FORM_TYPE_NOT_VISIBLE"


# --------------------------------------------------------------------------- #
# AC-CV4 / AC-CV5 / AC-CV7: the list
# --------------------------------------------------------------------------- #


def test_ac_cv4_lists_my_customers_contacts_with_a_chat_latest_first(world):
    resp = _client(world, world["agent_contact"]).get(BASE)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"]
    assert [r["contact_id"] for r in rows] == [world["chin"], world["lim"], world["tan"]]
    assert body["pagination"]["total"] == 3

    chin = rows[0]
    assert chin["customer_name"] == "Chin Chun Hardware"
    assert chin["contact_name"] == "Mr. Chin"
    assert chin["contact_phone"] == "+60123456789"
    assert chin["last_message_snippet"] == "Boss, the 60x60 grey tile got stock or not?"
    assert chin["last_message_direction"] == "incoming"
    assert chin["last_message_at"] == (BASE_TIME + timedelta(minutes=90)).isoformat()
    # The one key the thread is opened by; nothing else that is an id.
    for key in ("id", "customer_id", "respond_io_id", "sales_agent_id"):
        assert key not in chin, key

    tan = rows[2]
    assert tan["last_message_direction"] == "outgoing"
    assert tan["last_message_snippet"] == "Your price tag request PT-202609-0031 is ready."


def test_ac_cv4_a_contact_on_two_of_my_accounts_is_one_row_named_by_the_primary(world):
    rows = _client(world, world["agent_contact"]).get(BASE).json()["data"]
    tan_rows = [r for r in rows if r["contact_id"] == world["tan"]]
    assert len(tan_rows) == 1
    assert tan_rows[0]["customer_name"] == "Tan Home Living"


def test_ac_cv4_no_chat_no_respond_link_other_agent_and_other_company_are_not_rows(world):
    ids = {r["contact_id"] for r in _client(world, world["agent_contact"]).get(BASE).json()["data"]}
    for key in ("no_chat", "no_respond", "rival", "mocha_only"):
        assert world[key] not in ids, key


def test_ac_cv4_an_agent_with_no_conversations_gets_an_empty_list(world):
    db = world["db"]
    lonely_contact = _contact(db, "Agent Lonely")
    _agent(db, lonely_contact, "LON")
    _switch(db, lonely_contact, True)
    body = _client(world, lonely_contact).get(BASE).json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


def test_ac_cv9_the_search_matches_customer_contact_phone_and_last_message(world):
    client = _client(world, world["agent_contact"])

    def ids(q: str) -> list[str]:
        resp = client.get(BASE, params={"q": q})
        assert resp.status_code == 200, resp.text
        return [r["contact_id"] for r in resp.json()["data"]]

    assert ids("chin chun") == [world["chin"]]
    assert ids("ms. lim") == [world["lim"]]
    assert ids("0123456789") == [world["chin"]]
    assert ids("price tag") == [world["tan"]]
    assert ids("zzz-nothing") == []
    assert ids("%") == []  # literal, not a wildcard


def test_ac_cv4_paging(world):
    client = _client(world, world["agent_contact"])
    page2 = client.get(BASE, params={"page": 2, "limit": 2}).json()
    assert [r["contact_id"] for r in page2["data"]] == [world["tan"]]
    assert page2["pagination"]["total"] == 3


# --------------------------------------------------------------------------- #
# AC-CV12 / AC-CV13 / AC-CV14 / AC-CV16: the thread, in scope only
# --------------------------------------------------------------------------- #


def test_ac_cv12_the_page_is_the_crm_contact_page_for_the_same_contact(world):
    from app.services.sla_service import ConversationSLATrackingService

    client = _client(world, world["agent_contact"])
    got = client.get(f"{BASE}/{world['chin']}/page")
    assert got.status_code == 200, got.text
    expected = ConversationSLATrackingService(world["db"]).fetch_contact_thread_page(world["chin"])
    assert got.json() == expected
    assert [i["messageId"] for i in got.json()["items"]] == [
        1_700_000_000_000, 1_700_000_000_001, 1_700_000_000_090,
    ]


def test_ac_cv13_the_page_takes_the_same_cursors_and_refuses_two(world):
    client = _client(world, world["agent_contact"])
    older = client.get(f"{BASE}/{world['chin']}/page", params={"before": "1700000000090", "limit": 1})
    assert older.status_code == 200, older.text
    assert [i["messageId"] for i in older.json()["items"]] == [1_700_000_000_001]
    assert client.get(
        f"{BASE}/{world['chin']}/page", params={"before": "1", "after": "2"}
    ).status_code == 422


def test_ac_cv14_the_search_finds_messages_in_the_thread(world):
    client = _client(world, world["agent_contact"])
    got = client.get(f"{BASE}/{world['chin']}/search", params={"q": "60x60"})
    assert got.status_code == 200, got.text
    assert sorted(i["message_id"] for i in got.json()["items"]) == ["1700000000000", "1700000000090"]


def test_ac_cv12_comments_on_the_contact_come_back_and_another_contacts_do_not(world):
    db = world["db"]
    db.add(
        ConversationTicketComment(
            id=_uid(),
            tracking_id=None,
            respond_contact_id=world["chin"],
            author_name="Aina",
            body="Chin usually orders 40+ boxes.",
            mentioned_user_ids=[],
            source="crm",
            created_at=BASE_TIME + timedelta(minutes=5),
        )
    )
    db.add(
        ConversationTicketComment(
            id=_uid(),
            tracking_id=None,
            respond_contact_id=world["lim"],
            author_name="Aina",
            body="not for this thread",
            mentioned_user_ids=[],
            source="crm",
        )
    )
    db.flush()
    got = _client(world, world["agent_contact"]).get(f"{BASE}/{world['chin']}/comments")
    assert got.status_code == 200, got.text
    assert [c["body"] for c in got.json()] == ["Chin usually orders 40+ boxes."]


def test_ac_cv16_a_contact_outside_my_scope_is_404_on_every_thread_read(world):
    client = _client(world, world["agent_contact"])
    for who in ("rival", "mocha_only", "no_chat", "stranger"):
        for path in (
            f"{BASE}/{world[who]}/page",
            f"{BASE}/{world[who]}/search?q=hello",
            f"{BASE}/{world[who]}/comments",
        ):
            assert client.get(path).status_code == 404, (who, path)


def test_ac_cv16_the_thread_is_keyed_by_the_contact_id_only(world):
    """Never a phone number or a Respond id: a guessable key is a scope probe."""
    client = _client(world, world["agent_contact"])
    assert client.get(f"{BASE}/{_respond_io_id(world['db'], world['chin'])}/page").status_code == 404
    assert client.get(f"{BASE}/+60123456789/page").status_code == 404
    assert client.get(f"{BASE}/not-a-uuid/page").status_code == 404
