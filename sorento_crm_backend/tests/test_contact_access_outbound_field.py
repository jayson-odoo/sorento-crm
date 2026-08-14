"""The outbound switch has to reach the screens that manage contacts.

The Contact Access Agents grid (`GET /api/v1/user-management/access-agents/contact-access`)
and the contacts grid (`GET /api/v1/user-management/contacts/`) now show whether a
contact can be messaged, so both list bodies must carry
`respond_contacts.outbound_enabled` - and the grants grid must also carry
`respond_contact_id`, because one CONTACT owns many grant ROWS and the screen
has to know which rows belong to the same person before it de-duplicates a bulk
action.

Everything here asserts the ACTUAL response body, never the schema object: a
`response_model` silently drops any field the schema does not declare, and a
manual dict builder silently drops any field it does not list, so only the wire
format is evidence.

Run: pytest tests/test_contact_access_outbound_field.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.access import AccessAgent, ContactAgentAccess, RespondContact
from tests._pg_fixture import blank_session

GRANTS_URL = "/api/v1/user-management/access-agents/contact-access"
CONTACTS_URL = "/api/v1/user-management/contacts/"


@pytest.fixture
def db():
    with blank_session() as session:
        schema = session.get_bind()._execution_options["schema_translate_map"][None]
        session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        yield session


@pytest.fixture
def client(db):
    from app.database import get_db as database_get_db
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db as dependencies_get_db,
    )
    from app.main import app
    from app.services.user_service import UserPermissionService

    user = {"id": "zzt-admin"}
    app.dependency_overrides[database_get_db] = lambda: db
    app.dependency_overrides[dependencies_get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user

    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        UserPermissionService.check_user_has_permission = original
        app.dependency_overrides.clear()


def _contact(db, *, name: str, enabled: bool = True) -> RespondContact:
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+6011{str(uuid.uuid4().int)[:8]}",
        name=name,
        respond_io_id=str(uuid.uuid4().int)[:9],
        session_vars={},
        outbound_enabled=enabled,
    )
    db.add(row)
    db.commit()
    return row


def _agent(db, *, code: str) -> AccessAgent:
    row = AccessAgent(id=str(uuid.uuid4()), code=code, name=f"ZZT {code}")
    db.add(row)
    db.commit()
    return row


def _grant(db, contact: RespondContact, agent: AccessAgent) -> ContactAgentAccess:
    row = ContactAgentAccess(
        id=str(uuid.uuid4()),
        respond_contact_id=contact.id,
        respond_contact_phone=contact.phone_number,
        respond_contact_name=contact.name,
        agent_id=agent.id,
    )
    db.add(row)
    db.commit()
    return row


def _row_for(body: dict, grant_id: str) -> dict:
    return next(r for r in body["data"] if r["id"] == grant_id)


# --------------------------------------------------------------------------
# The grants grid - contact x agent rows
# --------------------------------------------------------------------------


def test_grant_row_carries_the_contacts_outbound_state(client, db):
    contact = _contact(db, name="ZZT Silenced", enabled=False)
    grant = _grant(db, contact, _agent(db, code="ZZT-A"))

    resp = client.get(GRANTS_URL)
    assert resp.status_code == 200, resp.text
    row = _row_for(resp.json(), grant.id)
    assert row["outbound_enabled"] is False


def test_grant_row_carries_outbound_true_for_a_reachable_contact(client, db):
    contact = _contact(db, name="ZZT Reachable", enabled=True)
    grant = _grant(db, contact, _agent(db, code="ZZT-B"))

    row = _row_for(client.get(GRANTS_URL).json(), grant.id)
    assert row["outbound_enabled"] is True


def test_grant_row_carries_the_contact_id_the_screen_de_duplicates_on(client, db):
    contact = _contact(db, name="ZZT Keyed", enabled=True)
    grant = _grant(db, contact, _agent(db, code="ZZT-C"))

    row = _row_for(client.get(GRANTS_URL).json(), grant.id)
    assert row["respond_contact_id"] == contact.id


def test_every_grant_for_one_contact_reports_the_same_switch(client, db):
    """One contact, three agents: three rows that must never disagree."""
    contact = _contact(db, name="ZZT Shared", enabled=False)
    grants = [
        _grant(db, contact, _agent(db, code=f"ZZT-D{i}")) for i in range(3)
    ]

    body = client.get(GRANTS_URL).json()
    rows = [_row_for(body, g.id) for g in grants]

    assert {r["respond_contact_id"] for r in rows} == {contact.id}
    assert [r["outbound_enabled"] for r in rows] == [False, False, False]


def test_two_contacts_keep_their_own_switch(client, db):
    on = _contact(db, name="ZZT On", enabled=True)
    off = _contact(db, name="ZZT Off", enabled=False)
    agent = _agent(db, code="ZZT-E")
    on_grant = _grant(db, on, agent)
    off_grant = _grant(db, off, agent)

    body = client.get(GRANTS_URL).json()
    assert _row_for(body, on_grant.id)["outbound_enabled"] is True
    assert _row_for(body, off_grant.id)["outbound_enabled"] is False


def test_a_grant_with_no_linked_contact_reports_no_switch(client, db):
    """Legacy rows are keyed by phone only. Unknown is null, never a cheerful True."""
    agent = _agent(db, code="ZZT-F")
    orphan = ContactAgentAccess(
        id=str(uuid.uuid4()),
        respond_contact_id=None,
        respond_contact_phone="+60110000001",
        respond_contact_name="ZZT Orphan",
        agent_id=agent.id,
    )
    db.add(orphan)
    db.commit()

    row = _row_for(client.get(GRANTS_URL).json(), orphan.id)
    assert row["respond_contact_id"] is None
    assert row["outbound_enabled"] is None


# --------------------------------------------------------------------------
# The contacts grid - one row per contact
# --------------------------------------------------------------------------


def test_contacts_list_carries_the_outbound_state(client, db):
    silenced = _contact(db, name="ZZT Contact Off", enabled=False)
    reachable = _contact(db, name="ZZT Contact On", enabled=True)

    resp = client.get(CONTACTS_URL)
    assert resp.status_code == 200, resp.text
    by_id = {r["id"]: r for r in resp.json()["data"]}

    assert by_id[silenced.id]["outbound_enabled"] is False
    assert by_id[reachable.id]["outbound_enabled"] is True
