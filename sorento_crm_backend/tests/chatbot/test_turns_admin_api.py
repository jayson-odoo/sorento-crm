"""S2b Phase 2: the turn trace admin API (AC-251 to AC-259, `chatbot-turn-engine`
acceptance criteria).

Written FIRST, before `app/api/v1/system/chatbot.py` exists at all - every test here is
expected to fail on a 404 (route not mounted) until the coder adds the router. That is
the RIGHT reason for red; a fixture bug would fail some other way (import error before
collection, or a 500 from a broken query), which is why each test also pins the
behaviour it wants once the route exists, not just "not 404".

Contract this is built against:
  - `sorento_crm_frontend/.../chat-history/services/chatbotTurnService.ts` (the Phase 1
    doc-comment contract): `GET /api/v1/system/chatbot/turns?contact_respond_id=&from=&
    to=&status=` -> `{items: [...], next_cursor}`; `POST .../{id}/retry` -> 403 without
    `system.chat_history.manage`, 409 unless `failed`, 200 `{turn_id, attempt}`.
  - AC-257 (list + retry), AC-255 (failed-contacts summary feeding the list's "Failed
    turns only" filter), AC-007/AC-003 (trace + response column shapes), R4 (manual
    retry only, no auto-retry), AC-705's retry re-injection.

CORRECTED FACT (from the coordinator, superseding this file's original assumption 4):
n8n's dispatcher redis is a SEPARATE instance on the n8n VPS and must not be touched from
here. The real pre-S7 retry path is an outbound HTTP POST to n8n's existing inject
webhook - `settings.chatbot_retry_ingress_url` (env `CHATBOT_RETRY_INGRESS_URL`,
production `https://automate-sorento.foundryx.my/webhook/sorento-main-inject`) - with the
ORIGINAL respond.io webhook body (`envelope.message`) and a shared
`X-Chatbot-Retry-Key` header from `settings.chatbot_retry_ingress_key` (env
`CHATBOT_RETRY_INGRESS_KEY`). `app/config.py` already carries both settings (added by the
S2b coder ahead of this file's update) with the note that an unset URL must answer 409
`retry_unavailable` and make NO call - a dev machine must never silently re-inject into
production n8n. `test_retry_reinjects_at_ingress` and `test_retry_unavailable_without_url`
below pin exactly that.

ASSUMPTIONS made because the contract doc does not spell these out (flagged to the
captain/coder, not settled unilaterally):

1. Pagination query params are named `limit` and `cursor` (opaque). The FE doc only
   shows `next_cursor` on the way OUT; the way IN is not named anywhere. Any reasonable
   name works for the coder - if it differs, these tests need a one-line rename, not a
   redesign.
2. `GET /api/v1/system/chatbot/turns/failed-contacts?from=&to=` is NOT in the FE
   contract doc at all - `chatbotTurnService.ts` documents only the two AC-257 routes.
   It exists in this file because the brief asked for it and because AC-255's "list
   shows contacts with a failed turn, with the last failed stage" needs an aggregate
   over potentially many thousands of contacts, which a per-row N+1 against `GET
   /turns` cannot do cheaply. Response shape assumed: `{"items": [{contact_respond_id,
   last_failed_stage, last_failed_at, count}]}`. This is the single biggest ambiguity
   in this file - see the report back to the captain.
3. Retry's idempotency-per-attempt (AC-257, "409 unless failed") is tested behaviourally
   only: call retry twice, first is 200, second is 409. The model DOES now carry a
   dedicated column for this (`chatbot.turns.retry_requested_at`, migration 474, added by
   the S2b coder): the row stays `failed` and a second click 409s because
   `retry_requested_at` is already set, not because `status` changed.
4. The outbound retry POST is mocked at `httpx.post` (module attribute) - the most direct
   patch target for a single fire-and-forget call. If the coder's endpoint imports
   `from httpx import post` instead of `import httpx; httpx.post(...)`, or reuses
   `app.services.webhook_service.WebhookService.send_webhook`, this patch target needs a
   one-line change to match - a coder implementation detail, not a fixture bug.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.config import settings
from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.chatbot_turn import ChatbotTurn
from app.services.user_service import UserPermissionService

RETRY_INGRESS_URL = "https://automate-sorento.foundryx.my/webhook/sorento-main-inject"
RETRY_INGRESS_KEY = "ZZT-retry-ingress-key"

VIEW = "system.chat_history.view"
MANAGE = "system.chat_history.manage"

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None, "name": "ZZT Turn Trace Tester"}


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db(session_factory):
    return session_factory()


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    """View-only by default; individual tests widen `_GRANTS` to add manage."""
    _GRANTS.clear()
    _GRANTS.add(VIEW)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(db):
    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(_ACTOR)
    _ACTOR["id"] = str(uuid.uuid4())
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def retry_ingress_configured(monkeypatch):
    """The retry endpoint's outbound target, configured to a fake n8n inject webhook.

    See module docstring assumption 4: the outbound POST is patched at `httpx.post`.
    """
    monkeypatch.setattr(settings, "chatbot_retry_ingress_url", RETRY_INGRESS_URL, raising=False)
    monkeypatch.setattr(settings, "chatbot_retry_ingress_key", RETRY_INGRESS_KEY, raising=False)
    mock_post = MagicMock(
        return_value=httpx.Response(200, request=httpx.Request("POST", RETRY_INGRESS_URL))
    )
    monkeypatch.setattr(httpx, "post", mock_post)
    return mock_post


@pytest.fixture()
def retry_ingress_unconfigured(monkeypatch):
    """The retry path with no n8n webhook configured (AC-705's 'unset locally on
    purpose' - a dev machine must never silently re-inject into production n8n)."""
    monkeypatch.setattr(settings, "chatbot_retry_ingress_url", None, raising=False)
    monkeypatch.setattr(settings, "chatbot_retry_ingress_key", None, raising=False)
    mock_post = MagicMock()
    monkeypatch.setattr(httpx, "post", mock_post)
    return mock_post


# --------------------------------------------------------------------------- #
# Seeding helpers                                                             #
# --------------------------------------------------------------------------- #


def _contact(label: str = "") -> str:
    return f"ZZT-contact-{label}-{uuid.uuid4().hex[:8]}"


def _trace_record(stage: str, *, status: str = "ok", summary: str = "", why: str = "", error: str | None = None) -> dict:
    return {
        "stage": stage,
        "status": status,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ms": 12,
        "summary": summary or f"{stage} ok",
        "why": why or f"{stage} reasoned fine",
        "facts": {},
        "error": error,
        "raw": {"note": "test payload"},
    }


def _seed_turn(
    db,
    *,
    contact_respond_id: str,
    status: str = "done",
    stage: str | None = None,
    branch_kind: str | None = None,
    trace: list[dict] | None = None,
    response: dict | None = None,
    message_id: str | None = None,
    attempt: int = 1,
    created_at: datetime | None = None,
    error: str | None = None,
) -> ChatbotTurn:
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_respond_id,
        message_id=message_id,
        ingress="webhook",
        envelope={"message": {"messageId": message_id}, "contact": {"id": contact_respond_id}},
        status=status,
        stage=stage,
        branch_kind=branch_kind,
        error=error,
        attempt=attempt,
        trace=trace if trace is not None else [],
        response=response,
    )
    if created_at is not None:
        turn.created_at = created_at
    db.add(turn)
    db.commit()
    return turn


BASE = "/api/v1/system/chatbot/turns"


# --------------------------------------------------------------------------- #
# AC-257: list auth + shape                                                   #
# --------------------------------------------------------------------------- #


def test_list_turns_requires_view_slug(client):
    """Without `system.chat_history.view`, 403 naming the slug; with it, 200."""
    _GRANTS.clear()  # withhold everything, including VIEW
    resp = client.get(BASE)
    assert resp.status_code == 403, resp.text
    assert VIEW in resp.text

    _GRANTS.add(VIEW)
    resp = client.get(BASE)
    assert resp.status_code == 200, resp.text


def test_list_turns_newest_first_paged(client, db):
    contact = _contact("paged")
    base_time = datetime.now(timezone.utc)
    turns = [
        _seed_turn(db, contact_respond_id=contact, created_at=base_time + timedelta(seconds=i))
        for i in range(3)
    ]
    # Oldest to newest: turns[0], turns[1], turns[2]. Newest-first page 1 of size 2
    # must be [turns[2], turns[1]].
    resp = client.get(BASE, params={"contact_respond_id": contact, "limit": 2})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    assert [item["id"] for item in body["items"]] == [turns[2].id, turns[1].id]
    assert body["next_cursor"] is not None

    resp2 = client.get(
        BASE,
        params={"contact_respond_id": contact, "limit": 2, "cursor": body["next_cursor"]},
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert [item["id"] for item in body2["items"]] == [turns[0].id]
    assert body2["next_cursor"] is None


def test_list_turns_filters(client, db):
    contact = _contact("filters")
    other_contact = _contact("filters-other")
    now = datetime.now(timezone.utc)

    in_range_failed = _seed_turn(
        db,
        contact_respond_id=contact,
        status="failed",
        stage="understood",
        created_at=now - timedelta(hours=1),
        error="parser timed out",
    )
    in_range_done = _seed_turn(
        db, contact_respond_id=contact, status="done", created_at=now - timedelta(minutes=30)
    )
    out_of_range = _seed_turn(
        db, contact_respond_id=contact, status="failed", created_at=now - timedelta(days=10)
    )
    _seed_turn(db, contact_respond_id=other_contact, status="failed", created_at=now)

    resp = client.get(BASE, params={"contact_respond_id": contact})
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {in_range_failed.id, in_range_done.id, out_of_range.id}

    resp = client.get(
        BASE,
        params={
            "contact_respond_id": contact,
            "from": (now - timedelta(hours=2)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {in_range_failed.id, in_range_done.id}

    resp = client.get(BASE, params={"contact_respond_id": contact, "status": "failed"})
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {in_range_failed.id, out_of_range.id}

    resp = client.get(BASE, params={"contact_respond_id": contact, "status": "not-a-real-status"})
    assert resp.status_code == 422, resp.text


def test_list_turns_carries_trace_and_response(client, db):
    """response_model must not silently drop trace[]/response fields
    (LESSONS-LEARNT: 'response_model silently drops undeclared fields')."""
    contact = _contact("shape")
    trace = [
        _trace_record("received", summary="Message received from WhatsApp"),
        _trace_record(
            "understood",
            status="failed",
            summary="Could not understand the message",
            why="the parser call raised",
            error="Provider timed out after 8s",
        ),
    ]
    response_body = {"ctx": {"foo": "bar"}, "item": None, "actions": []}
    turn = _seed_turn(
        db,
        contact_respond_id=contact,
        status="failed",
        stage="understood",
        trace=trace,
        response=response_body,
        error="Provider timed out after 8s",
    )

    resp = client.get(BASE, params={"contact_respond_id": contact})
    assert resp.status_code == 200, resp.text
    (item,) = [i for i in resp.json()["items"] if i["id"] == turn.id]

    assert len(item["trace"]) == 2
    understood = item["trace"][1]
    assert understood["summary"] == "Could not understand the message"
    assert understood["why"] == "the parser call raised"
    assert understood["error"] == "Provider timed out after 8s"
    assert understood["facts"] == {}
    assert understood["raw"] == {"note": "test payload"}
    assert item["response"] == response_body


# --------------------------------------------------------------------------- #
# AC-255: failed-contacts summary                                             #
# --------------------------------------------------------------------------- #


def test_failed_contacts_summary(client, db):
    now = datetime.now(timezone.utc)
    failed_contact = _contact("failed-summary")
    healthy_contact = _contact("healthy-summary")

    _seed_turn(
        db,
        contact_respond_id=failed_contact,
        status="failed",
        stage="looked_up",
        created_at=now - timedelta(hours=3),
        error="MCP call timed out",
    )
    last_failure = now - timedelta(hours=1)
    _seed_turn(
        db,
        contact_respond_id=failed_contact,
        status="failed",
        stage="access",
        created_at=last_failure,
        error="access service unavailable",
    )
    # A contact with ONLY successful turns must not appear.
    _seed_turn(db, contact_respond_id=healthy_contact, status="done", created_at=now)

    resp = client.get(
        f"{BASE}/failed-contacts",
        params={
            "from": (now - timedelta(days=1)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    contacts = {row["contact_respond_id"]: row for row in items}

    assert healthy_contact not in contacts
    assert failed_contact in contacts
    row = contacts[failed_contact]
    assert row["last_failed_stage"] == "access"
    assert row["count"] == 2
    assert row["last_failed_at"] is not None


# --------------------------------------------------------------------------- #
# AC-257: retry auth + guards + redis re-injection                            #
# --------------------------------------------------------------------------- #


def test_retry_requires_manage_slug(client, db):
    contact = _contact("retry-auth")
    turn = _seed_turn(db, contact_respond_id=contact, status="failed", stage="routed")

    resp = client.post(f"{BASE}/{turn.id}/retry")
    assert resp.status_code == 403, resp.text
    assert MANAGE in resp.text


def test_retry_only_failed(client, db, retry_ingress_configured):
    _GRANTS.add(MANAGE)
    contact = _contact("retry-guard")

    delegated_turn = _seed_turn(db, contact_respond_id=contact, status="delegated")
    resp = client.post(f"{BASE}/{delegated_turn.id}/retry")
    assert resp.status_code == 409, resp.text

    done_turn = _seed_turn(db, contact_respond_id=contact, status="done")
    resp = client.post(f"{BASE}/{done_turn.id}/retry")
    assert resp.status_code == 409, resp.text

    failed_turn = _seed_turn(db, contact_respond_id=contact, status="failed", stage="sent")
    resp = client.post(f"{BASE}/{failed_turn.id}/retry")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["turn_id"] == failed_turn.id
    assert body["attempt"] == 2


def test_retry_reinjects_at_ingress(client, db, retry_ingress_configured):
    """AC-705, corrected: n8n's dispatcher redis is a separate instance on the n8n VPS
    and must not be touched from here. Retry re-posts the ORIGINAL respond.io webhook
    body to n8n's inject webhook (`CHATBOT_RETRY_INGRESS_URL`) with the shared
    `X-Chatbot-Retry-Key` header, so the turn re-enters at the SAME ingress a live
    message uses. The row itself is NOT re-run in-process - it stays `failed`, and
    `retry_requested_at` records that a retry was requested."""
    _GRANTS.add(MANAGE)
    contact = _contact("retry-webhook")
    original_message = {
        "messageId": "wamid.ZZT-retry-webhook",
        "contactId": contact,
        "channelId": "whatsapp",
        "traffic": "incoming",
        "message": {"type": "text", "text": "price for SRTWC8517"},
    }
    turn = _seed_turn(
        db,
        contact_respond_id=contact,
        status="failed",
        stage="understood",
        message_id="wamid.ZZT-retry-webhook",
        error="parser timed out",
    )
    turn.envelope = {"message": original_message, "contact": {"id": contact}}
    db.commit()

    resp = client.post(f"{BASE}/{turn.id}/retry")
    assert resp.status_code == 200, resp.text

    retry_ingress_configured.assert_called_once()
    call = retry_ingress_configured.call_args
    called_url = call.args[0] if call.args else call.kwargs.get("url")
    assert called_url == RETRY_INGRESS_URL

    sent_body = call.kwargs.get("json")
    assert sent_body == original_message, (
        f"expected the ORIGINAL respond.io webhook body re-posted verbatim, got: {sent_body}"
    )

    sent_headers = call.kwargs.get("headers") or {}
    assert sent_headers.get("X-Chatbot-Retry-Key") == RETRY_INGRESS_KEY

    db.expire_all()
    reread = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn.id).one()
    # The row is a RECORD, not re-run: no turn happened in-process, so it stays `failed`,
    # and `retry_requested_at` is the marker (migration 474) that a retry went out.
    assert reread.status == "failed"
    assert reread.retry_requested_at is not None


def test_retry_unavailable_without_url(client, db, retry_ingress_unconfigured):
    """AC-705's own note: unset locally on purpose. With no
    `CHATBOT_RETRY_INGRESS_URL`, the endpoint must refuse with 409 `retry_unavailable`
    and make NO outbound call - a dev machine must never silently re-inject into
    production n8n."""
    _GRANTS.add(MANAGE)
    contact = _contact("retry-no-url")
    turn = _seed_turn(db, contact_respond_id=contact, status="failed", stage="access")

    resp = client.post(f"{BASE}/{turn.id}/retry")
    assert resp.status_code == 409, resp.text
    assert resp.json().get("code") == "retry_unavailable" or "retry_unavailable" in resp.text

    retry_ingress_unconfigured.assert_not_called()

    db.expire_all()
    reread = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn.id).one()
    assert reread.retry_requested_at is None


def test_retry_is_idempotent_per_attempt(client, db, retry_ingress_configured):
    """A second retry click before the retried turn has arrived must not double-inject."""
    _GRANTS.add(MANAGE)
    contact = _contact("retry-idempotent")
    turn = _seed_turn(db, contact_respond_id=contact, status="failed", stage="looked_up")

    first = client.post(f"{BASE}/{turn.id}/retry")
    assert first.status_code == 200, first.text

    second = client.post(f"{BASE}/{turn.id}/retry")
    assert second.status_code == 409, second.text
    retry_ingress_configured.assert_called_once()  # the second click made no new call
