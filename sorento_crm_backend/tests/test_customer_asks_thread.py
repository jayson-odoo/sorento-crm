"""ASKS-UX item 3 (AC-AU06 to AC-AU09): the opened ask reads the contact's FULL thread through
the shared conversation cores, on both mounts.

Routes: `GET /api/v1/public/portal/customer-asks/{id}/conversation/{page,search}` and
`GET /api/v1/sales/customer-asks/{id}/conversation/{page,search}`, same gate and scope as the
sibling `/conversation`. Respond is patched dead, so every page answers from `chat_histories`
(the local lane) and the assertions stay about scope and shape. `ask_message_ref` on
`/conversation` is the Respond `message_id` of the tagged row.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.models.base import set_company_scope
from app.models.price_tag import ContactPortalFormOverride
from app.models.user import User

from . import _ask_todo_seed as seed
from ._ask_todo_seed import ASK_AT, SORENTO
from ._pg_fixture import blank_session

PORTAL = "/api/v1/public/portal/customer-asks"
SALES = "/api/v1/sales/customer-asks"
VIEW = "sales.customer_asks.view"
M = timedelta(minutes=1)
PAGE_KEYS = {
    "items",
    "has_more_older",
    "has_more_newer",
    "oldest_message_id",
    "newest_message_id",
    "anchor_message_id",
    "limit",
    "source",
    "error",
    "backfilled",
}
SEARCH_KEYS = {"items", "total", "truncated", "query"}


class _DeadRespondClient:
    def list_messages(self, *a, **k):
        raise RuntimeError("Respond.io unreachable in tests")

    def get_message(self, *a, **k):
        raise RuntimeError("Respond.io unreachable in tests")


@pytest.fixture(autouse=True)
def _local_lane_only():
    with patch("app.services.integration_service.RespondClient") as client_cls:
        client_cls.return_value = _DeadRespondClient()
        client_cls.for_identifier.return_value = _DeadRespondClient()
        client_cls.for_contact_id.return_value = _DeadRespondClient()
        yield client_cls


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def w():
    """`conversation_world` plus Respond message ids on every row of the dealer's thread, a long
    older history (so a tail page cannot hold the ask), a stranger, a CRM user for the sales
    routes and a second agent's ask."""
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        world = seed.conversation_world(db)
        rid = world["rid"]
        # The plan 3.6 rows get ids so the thread can key them; the answer row is the anchor.
        for key, mid in (
            ("q_in", "20260929025000"),
            ("out_other", "20260929030100"),
            ("out_answer", "20260929030200"),
            ("out_late", "20260929032000"),
            ("too_early", "20260929022900"),
            ("too_late", "20260929033100"),
        ):
            db.execute(text("UPDATE chat_histories SET message_id = :m WHERE id = :i"), {"m": mid, "i": world[key].id})
        # 80 rows of older history, days before the ask (ids ascend with time): more than one 50-row page.
        world["history"] = [
            seed.chat(db, rid, ASK_AT - timedelta(days=3) + timedelta(minutes=i), "incoming", f"history {i}", message_id=f"2026092600{i:04d}")
            for i in range(80)
        ]
        world["stranger"] = seed.contact(db, "Not An Agent")
        for cid in (world["ca"], world["stranger"]):
            db.add(ContactPortalFormOverride(contact_id=cid, form_type="customer_asks", is_enabled=True))
        world["z_ask"] = seed.ask(db, world["z"], world["dealer"], "SRT-ZTHREAD", created_at=ASK_AT)
        uid = seed.uid()
        world["me"] = User(id=uid, email=f"{uid}@zzt.test", name="Alpha Person", status="ACTIVE", respond_contact_id=world["ca"])
        db.add(world["me"])
        db.flush()
        world["db"] = db
        db.commit()
        yield world


def _portal(w, contact_key="ca") -> TestClient:
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
    app.dependency_overrides[get_portal_token] = lambda: PortalToken(id=seed.uid(), contact_id=w[contact_key], space_id="zzt-space")
    return TestClient(app, headers={"X-Portal-Token": "zzt-token"}, raise_server_exceptions=False)


def _sales(w, permissions=(VIEW,)):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user = w["me"]
    actor = {"id": user.id, "email": user.email, "name": user.name, "role": "user"}
    app.dependency_overrides[get_db] = lambda: w["db"]
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    granted = list(permissions)
    originals = (UserPermissionService.check_user_has_permission, UserPermissionService.get_user_permission_slugs)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    client = TestClient(app, raise_server_exceptions=False)

    def restore():
        UserPermissionService.check_user_has_permission = originals[0]
        UserPermissionService.get_user_permission_slugs = originals[1]

    return client, restore


def _ids(page: dict) -> list[str]:
    return [str(i["messageId"]) for i in page["items"]]


# ---- AC-AU06: the page read ------------------------------------------------------------------


def test_portal_page_without_cursor_is_the_newest_window_oldest_first(w):
    resp = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/page")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == PAGE_KEYS
    ids = _ids(body)
    assert len(ids) == 50 and body["has_more_older"] is True and body["has_more_newer"] is False
    assert ids[-1] == "20260929033100"  # too_late is the newest row of the thread
    assert ids == sorted(ids)  # oldest first
    assert body["source"] == "local"
    # The other contact's row never leaks, whatever its time.
    assert "someone else's chat" not in resp.text


def test_portal_page_before_walks_older_and_around_centres(w):
    client = _portal(w)
    tail = client.get(f"{PORTAL}/{w['ask'].id}/conversation/page?limit=10").json()
    older = client.get(f"{PORTAL}/{w['ask'].id}/conversation/page?before={tail['oldest_message_id']}&limit=10").json()
    assert older["has_more_newer"] is True
    assert _ids(older)[-1] < tail["oldest_message_id"]
    around = client.get(f"{PORTAL}/{w['ask'].id}/conversation/page?around=20260929030200&limit=5").json()
    assert around["anchor_message_id"] == "20260929030200"
    assert _ids(around)[2] == "20260929030200"  # centred
    assert around["has_more_older"] is True


def test_two_cursors_at_once_is_422(w):
    resp = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/page?before=1&after=2")
    assert resp.status_code == 422


def test_sales_page_mirrors_the_portal_shape(w):
    client, restore = _sales(w)
    try:
        resp = client.get(f"{SALES}/{w['ask'].id}/conversation/page?limit=10")
        assert resp.status_code == 200, resp.text
        assert set(resp.json()) == PAGE_KEYS
        assert len(resp.json()["items"]) == 10
        assert client.get(f"{SALES}/{w['ask'].id}/conversation/page?before=1&around=2").status_code == 422
    finally:
        restore()


# ---- AC-AU07: search -------------------------------------------------------------------------


def test_portal_search_matches_newest_first_with_message_ids(w):
    resp = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/search?q=history 7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == SEARCH_KEYS
    hits = body["items"]
    assert hits and all(set(h) == {"message_id", "sent_at", "direction", "snippet"} for h in hits)
    # newest first: history i is at ASK_AT - 3d + i minutes, so 79 is the newest match and 7 the oldest
    assert [h["message_id"] for h in hits] == [f"2026092600{i:04d}" for i in range(79, 69, -1)] + ["20260926000007"]
    assert body["total"] == len(hits)
    none = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/search?q=someone else").json()
    assert none["items"] == []  # the other contact's row


def test_search_skips_rows_without_a_message_id(w):
    seed.chat(w["db"], w["rid"], ASK_AT + 40 * M, "incoming", "unkeyed needle")
    w["db"].commit()
    body = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/search?q=unkeyed needle").json()
    assert body["items"] == []


def test_sales_search_mirrors_the_portal(w):
    client, restore = _sales(w)
    try:
        resp = client.get(f"{SALES}/{w['ask'].id}/conversation/search?q=history 79")
        assert resp.status_code == 200, resp.text
        assert [h["message_id"] for h in resp.json()["items"]] == ["20260926000079"]
    finally:
        restore()


# ---- AC-AU08: gate and scope -----------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["page", "search?q=x"])
def test_portal_scope_and_gates(w, suffix):
    assert _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/{suffix}").status_code == 200  # positive control
    assert _portal(w).get(f"{PORTAL}/{w['z_ask'].id}/conversation/{suffix}").status_code == 404
    assert _portal(w).get(f"{PORTAL}/{seed.uid()}/conversation/{suffix}").status_code == 404
    assert _portal(w).get(f"{PORTAL}/not-a-uuid/conversation/{suffix}").status_code == 404
    stranger = _portal(w, "stranger").get(f"{PORTAL}/{w['ask'].id}/conversation/{suffix}")
    assert stranger.status_code == 403 and stranger.json().get("code") == "NOT_A_SALES_AGENT", stranger.text


@pytest.mark.parametrize("suffix", ["page", "search?q=x"])
def test_sales_scope_and_permission(w, suffix):
    client, restore = _sales(w)
    try:
        assert client.get(f"{SALES}/{w['ask'].id}/conversation/{suffix}").status_code == 200
        assert client.get(f"{SALES}/{w['z_ask'].id}/conversation/{suffix}").status_code == 404  # B's ask, no view_all
        assert client.get(f"{SALES}/{seed.uid()}/conversation/{suffix}").status_code == 404
    finally:
        restore()
    client, restore = _sales(w, permissions=())
    try:
        assert client.get(f"{SALES}/{w['ask'].id}/conversation/{suffix}").status_code == 403
    finally:
        restore()


def test_ask_without_a_thread_answers_the_empty_page_and_search(w):
    loose = seed.ask(w["db"], w["x"], None, "SRT-NOCONTACT", created_at=ASK_AT)
    bare_contact = seed.contact(w["db"], "No Respond Id")
    w["db"].execute(text("UPDATE respond_contacts SET respond_io_id = NULL WHERE id = :i"), {"i": bare_contact})
    bare = seed.ask(w["db"], w["x"], bare_contact, "SRT-BARE", created_at=ASK_AT)
    w["db"].commit()
    for ask in (loose, bare):
        page = _portal(w).get(f"{PORTAL}/{ask.id}/conversation/page")
        assert page.status_code == 200, page.text
        assert set(page.json()) == PAGE_KEYS and page.json()["items"] == [] and page.json()["error"]
        found = _portal(w).get(f"{PORTAL}/{ask.id}/conversation/search?q=history")
        assert found.status_code == 200 and found.json()["items"] == [] and found.json()["error"]


# ---- AC-AU09: the anchor ---------------------------------------------------------------------


def test_conversation_carries_the_anchors_respond_message_id(w):
    body = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation").json()
    assert body["ask_message_id"] == w["out_answer"].id
    assert body["ask_message_ref"] == "20260929030200"
    client, restore = _sales(w)
    try:
        crm = client.get(f"{SALES}/{w['ask'].id}/conversation").json()
        assert crm["ask_message_ref"] == "20260929030200"
        assert crm["contact_id"] == w["dealer"]
    finally:
        restore()


def test_anchor_ref_is_null_when_the_row_has_no_message_id_or_there_is_no_row(w):
    db = w["db"]
    db.execute(text("UPDATE chat_histories SET message_id = NULL WHERE id = :i"), {"i": w["out_answer"].id})
    db.commit()
    body = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation").json()
    assert body["ask_message_id"] == w["out_answer"].id and body["ask_message_ref"] is None
    db.execute(text("DELETE FROM chat_histories WHERE id IN (:a, :b, :c)"), {"a": w["out_other"].id, "b": w["out_answer"].id, "c": w["out_late"].id})
    db.commit()
    body = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation").json()
    assert body["ask_message_id"] is None and body["ask_message_ref"] is None


# ---- security review (30 Sep): cursors are message ids, the portal sees no staff identity ------


@pytest.mark.parametrize("cursor", ["../../id:999/message/list?limit=1#", "1?x=1", "abc"])
@pytest.mark.parametrize("name", ["before", "after", "around"])
def test_a_cursor_that_is_not_a_message_id_is_422_on_both_mounts(w, cursor, name):
    """A cursor reaches the Respond URL path (`RespondClient.get_message`); anything but digits
    is refused before it gets there."""
    from urllib.parse import quote

    resp = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/page?{name}={quote(cursor, safe='')}")
    assert resp.status_code == 422, resp.text
    client, restore = _sales(w)
    try:
        assert client.get(f"{SALES}/{w['ask'].id}/conversation/page?{name}={quote(cursor, safe='')}").status_code == 422
    finally:
        restore()


def test_the_core_refuses_a_cursor_that_is_not_a_message_id(w):
    from app.services import conversation_thread_service as svc

    contact = svc.ThreadContact(respond_io_id=w["rid"], phone_number="+60123456789")
    for name in ("before", "after", "around"):
        with pytest.raises(ValueError):
            svc.fetch_thread_page(w["db"], contact, **{name: "../../x"})
    assert svc.fetch_thread_page(w["db"], contact, around="20260929030200")["anchor_message_id"] == "20260929030200"


def test_portal_search_q_is_capped(w):
    assert _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/search?q={'a' * 201}").status_code == 422
    assert _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/search?q={'a' * 200}").status_code == 200


def test_portal_page_carries_no_staff_identity_or_transport_ids(w):
    from app.services.stock_ask_service import portal_thread_item

    raw = {
        "messageId": 1,
        "traffic": "outgoing",
        "message": {"type": "text", "text": "hi"},
        "sender": {"source": "user", "userId": 42, "name": "Sean Ibrahim", "contactId": 7},
        "status": [{"value": "read", "timestamp": 1}],
        "channelMessageId": "wamid.abc",
        "contactId": 9,
        "channelId": 3,
        "replyTo": {"messageId": 0, "message": {"text": "q"}},
        "source": "respond",
    }
    item = portal_thread_item(raw)
    assert item["sender"] == {"source": "user"}
    assert set(item) == {"messageId", "traffic", "message", "sender", "status", "replyTo", "source"}
    assert item["message"] == raw["message"] and item["status"] == raw["status"]
    # And through the route: every local-lane item comes back projected too.
    body = _portal(w).get(f"{PORTAL}/{w['ask'].id}/conversation/page?limit=5").json()
    assert body["items"]
    for it in body["items"]:
        assert set(it["sender"]) == {"source"}
        assert "channelMessageId" not in it and "contactId" not in it
