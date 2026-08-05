"""Who may see clearance dates (slice 4).

The risk this gate exists for: `/incoming-stock/list` and `crm_incoming_stock_list`
already serve salesperson- and dealer-facing agents. Adding ETA delay, CIDB
inspection/approval and gatepass to that response means that on the day it ships,
every one of those agents can answer questions it was never meant to answer.

Two properties carry the whole thing, and both are asserted here:

1. **An unentitled caller's response is byte-identical to today's.** Not "nulled",
   not "empty string" - the keys are ABSENT. Absent means "you may not see this";
   null means "not reached yet". An LLM reading the response will narrate a null as
   the latter, which is a lie with the confidence of a fact.
2. **A contact's question is answered with the CONTACT's entitlement**, never the
   API key's. n8n calls with a privileged act-as user; if that decided it, every
   contact would be entitled the moment n8n asked on their behalf.

Everything fails closed: unresolvable caller, inactive agent, expired grant, or a
lookup that raises.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.access import AccessAgent, ContactAgentAccess, RespondContact
from app.services.clearance_entitlement import (
    CLEARANCE_KEYS,
    CONTAINER_STATUS_AGENT_CODE,
    apply_clearance_gate,
    contact_is_entitled,
    is_entitled,
    strip_clearance,
    user_is_entitled,
)
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _agent(db, *, code=CONTAINER_STATUS_AGENT_CODE, active=True) -> AccessAgent:
    agent = AccessAgent(
        id=str(uuid.uuid4()),
        code=code,
        name="Container status enquiries",
        is_active=active,
    )
    db.add(agent)
    db.flush()
    return agent


def _contact(db) -> RespondContact:
    contact = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
    )
    db.add(contact)
    db.flush()
    return contact


def _grant(db, contact, agent, *, allowed=True, valid_from=None, valid_to=None):
    row = ContactAgentAccess(
        id=str(uuid.uuid4()),
        respond_contact_id=contact.id,
        respond_contact_phone=contact.phone_number,
        agent_id=agent.id,
        is_allowed=allowed,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(row)
    db.flush()
    return row


def _shipment_payload() -> dict:
    """The response shape as it exists TODAY, plus the new clearance keys."""
    return {
        "data": [
            {
                "shipment_number": "SHP-1",
                "shipping_container_number": "GXYU5106903",
                "estimated_arrival_date": "2026-07-18",
                "eta_delay_date": "2026-07-22",
                "gatepass_date": None,
                "liner_code": "CMA",
                "attachment": {"id": "att-1", "original_filename": "pl.pdf"},
                "lines": [
                    {"product_code": "P-1", "remaining_incoming_quantity": 5},
                ],
            }
        ],
        "empty": False,
        "pagination": {"total": 1, "page": 1, "limit": 10},
    }


#: What the endpoint returned before this slice. The regression test below asserts
#: an unentitled caller still gets exactly this.
TODAYS_SHAPE = {
    "data": [
        {
            "shipment_number": "SHP-1",
            "shipping_container_number": "GXYU5106903",
            "estimated_arrival_date": "2026-07-18",
            "attachment": {"id": "att-1", "original_filename": "pl.pdf"},
            "lines": [{"product_code": "P-1", "remaining_incoming_quantity": 5}],
        }
    ],
    "empty": False,
    "pagination": {"total": 1, "page": 1, "limit": 10},
}


# ------------------------------------------------------------------- stripping


def test_an_unentitled_response_is_byte_identical_to_todays(db):
    """The one assertion that says "shipping this breaks nothing"."""
    gated = apply_clearance_gate(db, _shipment_payload(), current_user={"id": None})
    assert gated == TODAYS_SHAPE


def test_clearance_keys_are_absent_not_null(db):
    """Absent means "you may not see this"; null means "not reached yet". An LLM
    reads a null as the second and says so out loud."""
    gated = apply_clearance_gate(db, _shipment_payload(), current_user={"id": None})
    row = gated["data"][0]

    for key in CLEARANCE_KEYS:
        assert key not in row, f"{key} must be absent, not present-and-null"
    # ...and specifically the one that was already null before stripping.
    assert "gatepass_date" not in row


def test_the_public_eta_still_flows(db):
    """`estimated_arrival_date` is today's ETA and the reason those agents exist.
    Stripping "anything ending in _date" would have taken it too."""
    gated = apply_clearance_gate(db, _shipment_payload(), current_user={"id": None})

    assert gated["data"][0]["estimated_arrival_date"] == "2026-07-18"
    assert "estimated_arrival_date" not in CLEARANCE_KEYS


def test_stripping_does_not_mutate_the_caller_s_payload():
    """The same row objects can be shared with another response or a cache."""
    payload = _shipment_payload()
    stripped = strip_clearance(payload)

    assert "eta_delay_date" not in stripped["data"][0]
    assert payload["data"][0]["eta_delay_date"] == "2026-07-22", "original untouched"


def test_stripping_reaches_nested_lists_and_dicts():
    nested = {"outer": [{"inner": {"eta_delay_date": "x", "keep": 1}}]}
    assert strip_clearance(nested) == {"outer": [{"inner": {"keep": 1}}]}


# ------------------------------------------------------------------ entitlement


def test_a_contact_holding_the_grant_is_entitled(db):
    contact = _contact(db)
    _grant(db, contact, _agent(db))

    assert contact_is_entitled(db, contact.id) is True


def test_a_contact_without_the_grant_is_not(db):
    contact = _contact(db)
    _agent(db)  # the agent exists, this contact simply does not hold it

    assert contact_is_entitled(db, contact.id) is False


def test_a_revoked_grant_does_not_entitle(db):
    contact = _contact(db)
    _grant(db, contact, _agent(db), allowed=False)

    assert contact_is_entitled(db, contact.id) is False


def test_an_expired_grant_does_not_entitle(db):
    contact = _contact(db)
    _grant(
        db,
        contact,
        _agent(db),
        valid_from=datetime.utcnow() - timedelta(days=30),
        valid_to=datetime.utcnow() - timedelta(days=1),
    )

    assert contact_is_entitled(db, contact.id) is False


def test_a_grant_that_has_not_started_does_not_entitle(db):
    contact = _contact(db)
    _grant(db, contact, _agent(db), valid_from=datetime.utcnow() + timedelta(days=1))

    assert contact_is_entitled(db, contact.id) is False


def test_deactivating_the_agent_revokes_everyone_at_once(db):
    contact = _contact(db)
    agent = _agent(db, active=False)
    _grant(db, contact, agent)

    assert contact_is_entitled(db, contact.id) is False


def test_holding_some_other_agent_does_not_entitle(db):
    contact = _contact(db)
    _grant(db, contact, _agent(db, code="stock_enquiries"))

    assert contact_is_entitled(db, contact.id) is False


def test_no_contact_id_is_not_entitled(db):
    assert contact_is_entitled(db, None) is False
    assert contact_is_entitled(db, "") is False


# ------------------------------------------------------- caller precedence


def test_a_contacts_question_uses_the_contacts_grant_not_the_api_keys(db, monkeypatch):
    """n8n calls with a privileged act-as user. If that decided it, every contact
    would be entitled the moment n8n asked on their behalf."""
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, u, s: True
    )
    contact = _contact(db)  # holds nothing

    assert is_entitled(db, current_user={"id": "privileged"}, contact_id=contact.id) is False
    # ...while the same privileged user asking for THEMSELVES still sees it.
    assert is_entitled(db, current_user={"id": "privileged"}) is True


def test_a_staff_user_without_the_permission_is_not_entitled(db, monkeypatch):
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, u, s: False
    )
    assert user_is_entitled(db, {"id": "someone"}) is False


def test_an_anonymous_caller_is_not_entitled(db):
    assert user_is_entitled(db, None) is False
    assert user_is_entitled(db, {}) is False


def test_a_lookup_that_raises_fails_closed(db, monkeypatch):
    """A broken permission service must not become an open door."""
    from app.services.user_service import UserPermissionService

    def _boom(self, user_id, slug):
        raise RuntimeError("permission service is down")

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _boom)
    assert user_is_entitled(db, {"id": "someone"}) is False


def test_an_entitled_caller_gets_the_payload_untouched(db, monkeypatch):
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, u, s: True
    )
    payload = _shipment_payload()

    assert apply_clearance_gate(db, payload, current_user={"id": "staff"}) == payload


# ---------------------------------------------------- the query must select them


def test_the_service_selects_every_gated_column():
    """`incoming_list` returns column tuples, not ORM instances.

    A clearance column missing from the SELECT reads as None on the row, and the
    gate would pass that straight through to an entitled caller as "not reached
    yet" - a silent wrong answer rather than a crash. This is the bug that shipped
    for one build.
    """
    import inspect

    from app.services import incoming_stock_service

    source = inspect.getsource(incoming_stock_service.IncomingStockService.incoming_list)
    assert "CLEARANCE_KEYS" in source, "the query must select the gated columns"
    # Both halves: selected in the query AND spread into the payload.
    assert source.count("CLEARANCE_KEYS") >= 2


def test_the_gate_runs_on_the_route_not_only_in_the_service():
    """The service returns everything by design, so the route is the single place
    entitlement is applied. If that call is ever dropped, the fields leak."""
    import inspect

    from app.api.v1 import incoming_stock

    source = inspect.getsource(incoming_stock.get_incoming_list)
    assert "apply_clearance_gate" in source
    assert "contact_id=contact_id" in source
