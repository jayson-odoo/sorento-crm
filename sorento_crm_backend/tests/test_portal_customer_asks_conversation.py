"""Sales asks to-do S3: the conversation around an ask, AC-ST309 and AC-ST310.

Service (`stock_ask_service.conversation_for_ask`) and the portal route
`GET /api/v1/public/portal/customer-asks/{id}/conversation`. `chat_histories.contact_id` carries
the contact's `respond_io_id` (not `respond_contacts.id`); the seed follows that.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.base import company_scope, set_company_scope
from app.models.price_tag import ContactPortalFormOverride

from . import _ask_todo_seed as seed
from ._ask_todo_seed import ASK_AT, SORENTO
from ._pg_fixture import blank_session

BASE = "/api/v1/public/portal/customer-asks"
M = timedelta(minutes=1)
MESSAGE_KEYS = {"id", "direction", "text", "at"}


@pytest.fixture
def w():
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        world = seed.conversation_world(db)
        world["stranger"] = seed.contact(db, "Not An Agent")
        world["off_contact"] = seed.contact(db, "Agent Off")
        seed.agent(db, world["off_contact"], "OFF")
        for cid, on in ((world["ca"], True), (world["stranger"], True), (world["off_contact"], False)):
            db.add(ContactPortalFormOverride(contact_id=cid, form_type="customer_asks", is_enabled=on))
        world["z_ask"] = seed.ask(db, world["z"], world["dealer"], "SRT-ZCONV", created_at=ASK_AT)
        world["db"] = db
        db.commit()
        yield world


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client(w, contact_id: str) -> TestClient:
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken
    from app.services.company_scope_resolver import apply_company_scope

    db = w["db"]

    async def _override_scope():
        set_company_scope(db, frozenset({SORENTO}))
        return frozenset({SORENTO})

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[apply_company_scope] = _override_scope
    app.dependency_overrides[get_portal_token] = lambda: PortalToken(
        id=seed.uid(), contact_id=contact_id, space_id="zzt-space"
    )
    return TestClient(app, headers={"X-Portal-Token": "zzt-token"}, raise_server_exceptions=False)


def _get(w, ask_id, contact_key="ca", query=""):
    return _client(w, w[contact_key]).get(f"{BASE}/{ask_id}/conversation{query}")


# ---- AC-ST309 -----------------------------------------------------------------------------


def test_window_rows_shape_and_isolation(w):
    resp = _get(w, w["ask"].id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"messages", "ask_message_id", "ask_message_ref"}
    ids = [m["id"] for m in body["messages"]]
    assert ids == [w["q_in"].id, w["out_other"].id, w["out_answer"].id, w["out_late"].id]  # oldest first
    for m in body["messages"]:
        assert set(m) == MESSAGE_KEYS, m
    first = body["messages"][0]
    assert (first["direction"], first["text"]) == ("in", "Got SRT-CONV? 10 pcs")
    assert body["messages"][1]["direction"] == "out"
    assert first["at"]  # a timestamp string
    excluded = {w[k].id for k in ("too_early", "too_late", "other_contact_row", "uuid_keyed_row")}
    assert excluded.isdisjoint(ids)


def test_ask_message_id_prefers_the_row_containing_the_answer_summary(w):
    assert _get(w, w["ask"].id).json()["ask_message_id"] == w["out_answer"].id


def test_ask_message_id_falls_back_to_the_nearest_outgoing_after_the_ask(w):
    w["db"].execute(text("UPDATE chat_histories SET message = 'no summary here' WHERE id = :i"), {"i": w["out_answer"].id})
    w["db"].commit()
    assert _get(w, w["ask"].id).json()["ask_message_id"] == w["out_other"].id


def test_ask_message_id_is_null_without_an_outgoing_row_after_the_ask(w):
    w["db"].execute(
        text("DELETE FROM chat_histories WHERE id IN (:a, :b, :c)"),
        {"a": w["out_other"].id, "b": w["out_answer"].id, "c": w["out_late"].id},
    )
    w["db"].commit()
    body = _get(w, w["ask"].id).json()
    assert body["ask_message_id"] is None
    assert [m["id"] for m in body["messages"]] == [w["q_in"].id]


def test_window_is_capped_at_60_rows(w):
    for i in range(70):
        seed.chat(w["db"], w["rid"], ASK_AT - timedelta(seconds=i + 1), "incoming", f"bulk {i}")
    w["db"].commit()
    assert len(_get(w, w["ask"].id).json()["messages"]) == 60


def test_ask_of_another_agent_is_404_and_gates_are_403(w):
    assert _get(w, w["ask"].id).status_code == 200  # positive control: the route exists
    assert _get(w, w["z_ask"].id).status_code == 404
    assert _get(w, seed.uid()).status_code == 404
    stranger = _get(w, w["ask"].id, "stranger")
    assert stranger.status_code == 403 and stranger.json().get("code") == "NOT_A_SALES_AGENT", stranger.text
    off = _get(w, w["ask"].id, "off_contact")
    assert off.status_code == 403 and off.json().get("code") == "FORM_TYPE_NOT_VISIBLE", off.text


def test_ask_with_no_contact_answers_an_empty_list(w):
    loose = seed.ask(w["db"], w["x"], None, "SRT-NOCONTACT", created_at=ASK_AT)
    w["db"].commit()
    resp = _get(w, loose.id)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"messages": [], "ask_message_id": None, "ask_message_ref": None}


def test_contact_without_a_respond_io_id_answers_an_empty_list(w):
    bare = seed.contact(w["db"], "No Respond Id")
    w["db"].execute(text("UPDATE respond_contacts SET respond_io_id = NULL WHERE id = :i"), {"i": bare})
    ask = seed.ask(w["db"], w["x"], bare, "SRT-BARE", created_at=ASK_AT)
    seed.chat(w["db"], "", ASK_AT, "incoming", "an empty-id row must not match")
    w["db"].commit()
    resp = _get(w, ask.id)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"messages": [], "ask_message_id": None, "ask_message_ref": None}


def test_service_contract_conversation_for_ask(w):
    from app.services import stock_ask_service

    out = stock_ask_service.conversation_for_ask(w["db"], w["ask"])
    assert set(out) == {"messages", "ask_message_id", "ask_message_ref", "contact_id"}
    assert [m["id"] for m in out["messages"]][0] == w["q_in"].id
    assert out["ask_message_id"] == w["out_answer"].id
    assert {m["direction"] for m in out["messages"]} == {"in", "out"}


# ---- AC-ST310 -----------------------------------------------------------------------------


def test_whole_day_widens_to_the_malaysia_calendar_day(w):
    db, rid = w["db"], w["rid"]
    before_day = seed.chat(db, rid, seed.TODAY_START - timedelta(seconds=1), "incoming", "previous MY day")
    early = seed.chat(db, rid, ASK_AT - timedelta(hours=5), "incoming", "morning")
    last = seed.chat(db, rid, ASK_AT + timedelta(hours=13) - M, "outgoing", "end of day")
    next_day = seed.chat(db, rid, ASK_AT + timedelta(hours=13), "incoming", "next MY day")
    db.commit()
    resp = _get(w, w["ask"].id, query="?whole_day=true")
    assert resp.status_code == 200, resp.text
    ids = [m["id"] for m in resp.json()["messages"]]
    assert early.id in ids and last.id in ids
    assert w["too_early"].id in ids and w["too_late"].id in ids  # same day, outside the 30 minutes
    assert before_day.id not in ids and next_day.id not in ids
    assert w["other_contact_row"].id not in ids
    assert ids == sorted(ids, key=lambda i: next(m["at"] for m in resp.json()["messages"] if m["id"] == i))
    assert resp.json()["ask_message_id"] == w["out_answer"].id
    narrow = [m["id"] for m in _get(w, w["ask"].id, query="?whole_day=false").json()["messages"]]
    assert early.id not in narrow


def test_whole_day_is_capped_at_200_rows(w):
    for i in range(210):
        seed.chat(w["db"], w["rid"], ASK_AT - timedelta(seconds=i + 1), "incoming", f"bulk {i}")
    w["db"].commit()
    assert len(_get(w, w["ask"].id, query="?whole_day=true").json()["messages"]) == 200


def test_ask_message_id_is_never_an_id_absent_from_messages(w):
    """70 outgoing rows fill the window; the matching answer row can fall outside the 60 returned."""
    db = w["db"]
    db.execute(text("DELETE FROM chat_histories WHERE id = :i"), {"i": w["out_answer"].id})
    for i in range(70):
        seed.chat(db, w["rid"], ASK_AT + timedelta(seconds=10 + i), "outgoing", f"filler {i}")
    late_answer = seed.chat(db, w["rid"], ASK_AT + timedelta(minutes=25), "outgoing", w["ask"].answer_summary)
    db.commit()
    body = _get(w, w["ask"].id).json()
    ids = [m["id"] for m in body["messages"]]
    assert len(ids) == 60
    assert body["ask_message_id"] is None or body["ask_message_id"] in ids
    assert late_answer.id not in ids or body["ask_message_id"] in (None, late_answer.id)


def test_customerless_ask_in_another_company_has_no_conversation(w):
    from app.services.company_scope_resolver import apply_company_scope

    db = w["db"]
    cw = seed.cross_company_world(db, w)
    db.commit()
    client = _client(w, w["ca"])

    async def _both():
        set_company_scope(db, frozenset({SORENTO, cw["mocha"].id}))
        return frozenset({SORENTO, cw["mocha"].id})

    app.dependency_overrides[apply_company_scope] = _both
    assert client.get(f"{BASE}/{cw['loose'].id}/conversation").status_code == 200  # control
    assert client.get(f"{BASE}/{cw['foreign'].id}/conversation").status_code == 404
