"""WA-USERNAME-CONTACTS core service tests (red first). UAC WU1-WU19, plan test list items 1-4 and 14.

Plan: documentation/plans/contacts/PLAN-wa-username-contacts-26oct.md. The module under test is
`app.services.wa_phone_link`; it is imported inside each test so every test fails on its own.
Fake data only (public repo). No test reaches Respond.io: the client is a recording fake, and
`merge_contacts` runs over an httpx MockTransport.
"""
from __future__ import annotations

import copy
import logging
import uuid

import httpx
import pytest

from tests._pg_fixture import blank_session

TURN_ID = 900000002
PHONE_ID = 900000003
E164 = "60100000001"

TAP = {
    "event_type": "message.received",
    "contact": {"id": TURN_ID, "phone": None, "firstName": "CONTACT B"},
    "message": {
        "messageId": 1700000000000001,
        "contactId": TURN_ID,
        "traffic": "incoming",
        "timestamp": 1700000000000,
        "sender": {"source": "contact"},
        "message": {
            "type": "contact",
            "contact": {
                "cId": 1,
                "phone": "+60100000001",
                "origin": "contact_request",
                "payload": None,
                "firstName": "CONTACT A",
            },
        },
    },
    "channel": {"source": "whatsapp", "meta": {"wa_id": "60100000001", "user_id": "MY.0000000000000001"}},
}


def _tap(**card):
    body = copy.deepcopy(TAP)
    for key, value in card.items():
        if value is _MISSING:
            body["message"]["message"]["contact"].pop(key, None)
        else:
            body["message"]["message"]["contact"][key] = value
    return body


_MISSING = object()


def _shared():
    body = _tap(phone="+60100000002", origin="other")
    return body


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(self, request):
        raise AssertionError(f"real network call attempted: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _boom)


def _mod():
    from app.services import wa_phone_link

    return wa_phone_link


class FakeClient:
    """Records every call. `phone_contact_id` None = Respond.io has no contact for the phone (404)."""

    def __init__(self, phone_contact_id=PHONE_ID, *, lookup_error=None, merge_error=None, put_error=None, wrapped=False):
        self.wrapped = wrapped
        self.phone_contact_id = phone_contact_id
        self.lookup_error = lookup_error
        self.merge_error = merge_error
        self.put_error = put_error
        self.calls: list[tuple] = []

    def get_contact_by_phone(self, phone):
        self.calls.append(("lookup", phone))
        if self.lookup_error is not None:
            raise self.lookup_error
        if self.phone_contact_id is None:
            req = httpx.Request("GET", "https://api.example.test/v2/contact/phone")
            raise httpx.HTTPStatusError("not found", request=req, response=httpx.Response(404, request=req))
        record = {"id": self.phone_contact_id, "phone": f"+{E164}"}
        return {"data": record} if self.wrapped else record

    def merge_contacts(self, contact_ids):
        self.calls.append(("merge", [int(x) for x in contact_ids]))
        if self.merge_error is not None:
            raise self.merge_error
        return {"id": contact_ids[0]}

    def update_contact(self, identifier, payload):
        self.calls.append(("put", str(identifier).replace("id:", ""), payload))
        if self.put_error is not None:
            raise self.put_error
        return {}

    def kinds(self):
        return [c[0] for c in self.calls]


def _http_error(status):
    req = httpx.Request("POST", "https://api.example.test/v2/contact/merge")
    return httpx.HTTPStatusError("boom", request=req, response=httpx.Response(status, request=req))


def _workspace(db):
    from app.models.respond_workspace import RespondWorkspace

    ws = RespondWorkspace(space_id=f"sp{uuid.uuid4().hex[:6]}", api_key_ciphertext="x", is_default=True)
    db.add(ws)
    db.commit()
    return ws


def _agent(db):
    from sqlalchemy import text

    aid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO access_agents (id, code, name, is_active, assign_to_new_internal_contacts, "
            "created_at, updated_at, synced_to_excel) VALUES (:id, :c, 'zzt', true, true, now(), now(), false)"
        ),
        {"id": aid, "c": f"zzt_{aid[:8]}"},
    )
    db.commit()
    return aid


def _row(db, phone, *, respond_io_id=str(PHONE_ID), allowed=True, workspace_id=None):
    from app.models.access import RespondContact

    row = RespondContact(
        phone_number=phone, respond_io_id=respond_io_id, chatbot_allowed=allowed, workspace_id=workspace_id
    )
    db.add(row)
    db.commit()
    return row


def _rows(db):
    from app.models.access import RespondContact

    return db.query(RespondContact).all()


# ---------------------------------------------------------------- 1. accepted_card_phone


def test_wu11_is_contact_card_true_for_contact_type():
    m = _mod()
    assert m.is_contact_card(_tap()) is True
    assert m.is_contact_card(_shared()) is True


def test_wu1_is_contact_card_false_for_text():
    m = _mod()
    body = copy.deepcopy(TAP)
    body["message"]["message"] = {"type": "text", "text": "hello"}
    assert m.is_contact_card(body) is False


def test_wu11_accepted_card_phone_tap_returns_e164_digits():
    assert _mod().accepted_card_phone(_tap()) == E164


def test_wu10_hand_shared_card_is_not_accepted():
    # origin other, and wa_id (sender's own number) differs from the card phone
    assert _mod().accepted_card_phone(_shared()) is None


def test_wu10_origin_missing_is_not_accepted():
    assert _mod().accepted_card_phone(_tap(origin=_MISSING)) is None


def test_wu10_origin_other_with_matching_wa_id_is_not_accepted():
    assert _mod().accepted_card_phone(_tap(origin="other")) is None


def test_wu10_wa_id_different_is_not_accepted():
    body = _tap()
    body["channel"]["meta"]["wa_id"] = "60100000009"
    assert _mod().accepted_card_phone(body) is None


def test_wu11_wa_id_absent_with_good_origin_is_accepted():
    body = _tap()
    del body["channel"]["meta"]["wa_id"]
    assert _mod().accepted_card_phone(body) == E164
    body2 = _tap()
    del body2["channel"]
    assert _mod().accepted_card_phone(body2) == E164


@pytest.mark.parametrize("empty", ["", None, "   "])
def test_wu10_empty_phone_is_not_accepted(empty):
    assert _mod().accepted_card_phone(_tap(phone=empty)) is None


def test_wu10_non_contact_type_is_not_accepted():
    body = copy.deepcopy(TAP)
    body["message"]["message"] = {"type": "text", "text": "60100000001"}
    assert _mod().accepted_card_phone(body) is None


@pytest.mark.parametrize("phone", ["+60100000001", "60100000001", "+60 10-000 0001"])
def test_wu11_phone_formats_normalise_equal(phone):
    body = _tap(phone=phone)
    assert _mod().accepted_card_phone(body) == E164


def test_wu11_bare_wa_id_matches_plus_phone_and_reverse():
    body = _tap(phone="60100000001")
    body["channel"]["meta"]["wa_id"] = "+60100000001"
    assert _mod().accepted_card_phone(body) == E164


# ---------------------------------------------------------------- 2. link_phone


@pytest.mark.parametrize("wrapped", [False, True], ids=["bare", "data_wrapped"])
def test_wu12_phone_contact_with_crm_row_merges_and_row_unchanged(wrapped):
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        row = _row(db, f"+{E164}", allowed=True, workspace_id=str(ws.id))
        pk = str(row.id)
        client = FakeClient(wrapped=wrapped)
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "merged"
        assert ("merge", [PHONE_ID, TURN_ID]) in client.calls
        assert "put" not in client.kinds()
        assert out.survivor_respond_id == str(PHONE_ID)
        assert out.contact_pk == pk
        assert out.chatbot_allowed is True
        rows = _rows(db)
        assert len(rows) == 1 and str(rows[0].id) == pk and rows[0].respond_io_id == str(PHONE_ID)


def test_wu12_chatbot_allowed_false_is_reported():
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        _row(db, f"+{E164}", allowed=False, workspace_id=str(ws.id))
        out = m.link_phone(db, FakeClient(), contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "merged" and out.chatbot_allowed is False


def test_wu12_phone_contact_without_crm_row_merges_and_creates_row():
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        agent_id = _agent(db)
        client = FakeClient()
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "merged"
        assert ("merge", [PHONE_ID, TURN_ID]) in client.calls
        rows = _rows(db)
        assert len(rows) == 1
        assert rows[0].phone_number.lstrip("+") == E164
        assert rows[0].respond_io_id == str(PHONE_ID)
        assert str(rows[0].workspace_id) == str(ws.id)
        assert out.chatbot_allowed is False
        from app.models.access import ContactAgentAccess

        access = db.query(ContactAgentAccess).filter(ContactAgentAccess.respond_contact_id == rows[0].id).all()
        assert [str(a.agent_id) for a in access] == [agent_id]


def test_wu14_no_respond_contact_sets_phone_and_creates_row():
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        agent_id = _agent(db)
        client = FakeClient(phone_contact_id=None)
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "phone_set"
        assert "merge" not in client.kinds()
        assert ("put", str(TURN_ID), {"phone": f"+{E164}"}) in client.calls
        rows = _rows(db)
        assert len(rows) == 1 and rows[0].respond_io_id == str(TURN_ID)
        assert rows[0].phone_number.lstrip("+") == E164
        assert str(rows[0].workspace_id) == str(ws.id)
        assert out.survivor_respond_id == str(TURN_ID)
        from app.models.access import ContactAgentAccess

        n = db.query(ContactAgentAccess).filter(ContactAgentAccess.respond_contact_id == rows[0].id).count()
        assert n == 1 and agent_id


def test_wu14_no_respond_contact_existing_row_is_repointed():
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        row = _row(db, f"+{E164}", respond_io_id="900000077", allowed=True, workspace_id=str(ws.id))
        pk = str(row.id)
        out = m.link_phone(db, FakeClient(phone_contact_id=None), contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "phone_set"
        rows = _rows(db)
        assert len(rows) == 1 and str(rows[0].id) == pk and rows[0].respond_io_id == str(TURN_ID)
        assert out.chatbot_allowed is True


@pytest.mark.parametrize(
    "client",
    [
        FakeClient(merge_error=_http_error(500)),
        FakeClient(phone_contact_id=None, put_error=_http_error(500)),
        FakeClient(lookup_error=_http_error(500)),
        FakeClient(lookup_error=httpx.ReadTimeout("slow")),
    ],
    ids=["merge_error", "put_error", "lookup_500", "lookup_timeout"],
)
def test_wu16_respond_failure_writes_nothing_in_crm(client):
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        row = _row(db, f"+{E164}", respond_io_id="900000077", workspace_id=str(ws.id))
        before = (str(row.id), row.respond_io_id)
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "failed"
        assert out.reason
        rows = _rows(db)
        assert [(str(r.id), r.respond_io_id) for r in rows] == [before]


def test_wu16_failure_with_no_row_creates_no_row():
    m = _mod()
    with blank_session() as db:
        _workspace(db)
        out = m.link_phone(db, FakeClient(merge_error=_http_error(500)), contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "failed"
        assert _rows(db) == []


def test_wu16_two_crm_rows_for_the_phone_fail_before_any_respond_write():
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        _row(db, E164, respond_io_id="900000071", workspace_id=str(ws.id))
        _row(db, f"+{E164}", respond_io_id="900000072", workspace_id=str(ws.id))
        client = FakeClient()
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "failed"
        assert "merge" not in client.kinds() and "put" not in client.kinds()
        assert sorted(r.respond_io_id for r in _rows(db)) == ["900000071", "900000072"]


def test_wu16_row_on_non_default_workspace_fails_with_no_write():
    from app.models.respond_workspace import RespondWorkspace

    m = _mod()
    with blank_session() as db:
        _workspace(db)
        other = RespondWorkspace(space_id="other1", api_key_ciphertext="x", is_default=False)
        db.add(other)
        db.commit()
        _row(db, f"+{E164}", respond_io_id="900000077", workspace_id=str(other.id))
        client = FakeClient()
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert out.status == "failed"
        assert "merge" not in client.kinds() and "put" not in client.kinds()
        assert [r.respond_io_id for r in _rows(db)] == ["900000077"]


def test_wu12_phone_contact_id_equal_turn_id_means_no_merge():
    m = _mod()
    with blank_session() as db:
        ws = _workspace(db)
        _row(db, f"+{E164}", respond_io_id="900000077", workspace_id=str(ws.id))
        client = FakeClient(phone_contact_id=TURN_ID)
        out = m.link_phone(db, client, contact_respond_id=str(TURN_ID), phone=E164)
        assert "merge" not in client.kinds()
        assert out.status != "failed"
        assert [r.respond_io_id for r in _rows(db)] == [str(TURN_ID)]


# ---------------------------------------------------------------- 3. merge_contacts request


def test_wu12_merge_contacts_builds_the_v2_merge_request(monkeypatch):
    from app.services.integration_service import RespondClient

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"contactId": PHONE_ID})

    monkeypatch.setattr(
        RespondClient,
        "_http",
        staticmethod(lambda timeout=15: httpx.Client(transport=httpx.MockTransport(handler))),
    )
    client = RespondClient(api_key="k-test", base_url="https://api.example.test", space_id="sp1")
    out = client.merge_contacts([str(PHONE_ID), TURN_ID])
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.example.test/v2/contact/merge"
    assert seen["json"] == {"contactIds": [PHONE_ID, TURN_ID]}
    assert seen["auth"] and seen["auth"].endswith("k-test")
    assert isinstance(out, dict)


def test_wu12_merge_contacts_raises_on_http_error(monkeypatch):
    from app.services.integration_service import RespondClient

    monkeypatch.setattr(
        RespondClient,
        "_http",
        staticmethod(
            lambda timeout=15: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={})))
        ),
    )
    client = RespondClient(api_key="k-test", base_url="https://api.example.test", space_id="sp1")
    with pytest.raises(httpx.HTTPStatusError):
        client.merge_contacts([PHONE_ID, TURN_ID])


# ---------------------------------------------------------------- 4. logs


def test_wu18_logs_never_carry_the_full_phone(caplog):
    m = _mod()
    caplog.set_level(logging.DEBUG)
    with blank_session() as db:
        ws = _workspace(db)
        _row(db, f"+{E164}", workspace_id=str(ws.id))
        m.accepted_card_phone(_tap())
        m.link_phone(db, FakeClient(), contact_respond_id=str(TURN_ID), phone=E164)
        m.link_phone(
            db,
            FakeClient(merge_error=RuntimeError(f"boom for +{E164}")),
            contact_respond_id=str(TURN_ID),
            phone=E164,
        )
    assert E164 not in caplog.text


# ---------------------------------------------------------------- 14. use case


def test_wu6_wa_phone_share_is_a_template_default_use_case():
    from app.models.respond_template import TEMPLATE_DEFAULT_USE_CASES

    assert "wa_phone_share" in TEMPLATE_DEFAULT_USE_CASES
