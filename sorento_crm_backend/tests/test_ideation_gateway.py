"""IDEATION-IN-CRM: the ``/api/v1/ideation`` gateway (CRM backend -> ss embed API).

Red tests, written BEFORE the implementation, from
``documentation/plans/ideation/ideation-in-crm-acceptance-criteria.md`` (A-01..A-09) and PLAN
sections 10 and 13.

CONTRACT the coder must build to (the names these tests import or exercise):

* Router mounted at ``/api/v1/ideation`` (module guard like every domain), routes per AC-A-08.
* Service module ``app.services.ideation_gateway_service`` exposing
  - ``get_embed_token(db, user: dict, *, force_refresh: bool = False) -> str``: mints the
    assertion via ``ideation_embed_service.mint_embed_assertion``, exchanges it at ss
    ``POST /embed/session``, caches per ``user["id"]`` until 30 s before ``expires_at``.
    Raises ``IdeationEmbedNotConfigured`` / ``IdeationEmbedUpstreamError`` (reused from
    ``app.services.ideation_embed_service``) when dormant / ss unreachable.
  - ``clear_token_cache() -> None``.
* ss is reached with a SYNC ``httpx.Client`` (everything goes through ``httpx.Client.send``;
  that is the boundary ``tests/_ideation_ss_fake.py`` patches). ss auth = ``Authorization:
  Bearer <embed token>``.
* Permission checks go through ``UserPermissionService.check_user_has_permission`` (what
  ``require_permission`` uses) with slugs ``ideation.board.view`` (view) and
  ``ideation.ideas.manage`` (manage).
* Pending-action keys ``idea.archive`` (reversible window) and ``idea.delete`` (destructive
  window), entity type ``idea``, permission ``ideation.ideas.manage``, registered in
  ``app.services.record_actions``; the handler reads ``payload["entity_id"]`` and
  ``payload["requested_by_id"]`` and calls ss as that user.
* Pending-action key ``idea_comment.delete`` (destructive window), entity type ``idea_comment``
  (``entity_id`` = comment id), permission ``ideation.board.view`` (any viewer may park the
  delete of a comment; ss decides whether it is theirs), payload ``{"idea_id": ...}``; the handler
  calls ss ``DELETE /embed/ideas/{idea_id}/comments/{entity_id}`` as the requester. Not in the
  UAC's A-09 text, but AC-E-03's 10 s countdown needs it (the FE test pins the same key).

Postgres only (``tests/_pg_fixture.py``), ss faked at httpx, no network.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.config import settings
from app.models.user import User
from tests._ideation_ss_fake import (
    CONNECTION_ID,
    SIGNING_SECRET,
    FakeSS,
    blank_embed_settings,
    configure_embed_settings,
    message_of,
)
from tests._pg_fixture import blank_session

VIEW = "ideation.board.view"
MANAGE = "ideation.ideas.manage"
BASE = "/api/v1/ideation"
IDEA = "7c1d0b7e-0000-4000-8000-00000000a001"
IDEA_B = "7c1d0b7e-0000-4000-8000-00000000a002"
COMMENT = "9d2e1c8f-0000-4000-8000-00000000c001"
ATT = "5b3f2a9e-0000-4000-8000-00000000d001"
UNREACHABLE = "The Ideas workspace isn't reachable right now."
UNAVAILABLE = "The Ideas workspace isn't available on this deployment."


class Env:
    def __init__(self, client, fake, db, allow):
        self.client = client
        self.fake = fake
        self.db = db
        self.allow = allow
        self.user: dict = {}

    def login(self, *, name: str | None = "Alice Tan", email: str | None = None) -> dict:
        """Seed a real user row and make it the caller. Unique id per call, so the
        process-wide token cache can never leak between tests."""
        uid = str(uuid.uuid4())
        email = email if email is not None else f"zzt-{uid[:8]}@example.test"
        self.db.add(User(id=uid, email=email, name=name, status="ACTIVE"))
        self.db.commit()
        self.user = {"id": uid, "email": email, "name": name}
        return self.user

    def req(self, method: str, path: str, **kw):
        return self.client.request(method, f"{BASE}{path}", **kw)


@pytest.fixture
def env(monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    configure_embed_settings(monkeypatch)
    fake = FakeSS().install(monkeypatch)
    allow: set[str] = {VIEW, MANAGE}

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow
    )
    monkeypatch.setattr(
        UserPermissionService, "get_user_permission_slugs", lambda self, uid: list(allow)
    )

    with blank_session() as db:
        def _db():
            yield db

        holder: dict = {}
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: dict(holder["user"])
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(holder["user"])
        app.dependency_overrides[apply_company_scope] = lambda: None
        try:
            # No ``with``: entering the client would run the app's startup events per test.
            client = TestClient(app)
            e = Env(client, fake, db, allow)
            real_login = e.login

            def _login(**kw):
                holder["user"] = real_login(**kw)
                return holder["user"]

            e.login = _login  # type: ignore[method-assign]
            e.login()
            yield e
        finally:
            app.dependency_overrides.clear()


def _ss_called(e: Env) -> bool:
    return bool(e.fake.calls or e.fake.session_calls)


# --------------------------------------------------------------------------- #
# The AC-A-08 route map                                                        #
# --------------------------------------------------------------------------- #
# id, crm method, crm path, request kwargs, needs manage?, ss method, ss path, ss query,
# expected ss json body (None = no body asserted), ss status
_ROUTES = [
    ("list", "GET", "/ideas?filter=archived", {}, False, "GET", "/embed/ideas", {"filter": "archived"}, None, 200),
    ("board", "GET", "/ideas/board", {}, False, "GET", "/embed/board", {}, None, 200),
    ("get", "GET", f"/ideas/{IDEA}", {}, False, "GET", f"/embed/ideas/{IDEA}", {}, None, 200),
    ("merged", "GET", f"/ideas/{IDEA}/merged", {}, False, "GET", f"/embed/ideas/{IDEA}/merged", {}, None, 200),
    (
        "create", "POST", "/ideas",
        {"json": {"problem": "Slow quotes", "proposedSolution": "Templates", "rawText": "raw"}}, False,
        "POST", "/embed/ideas", {}, {"problem": "Slow quotes", "proposedSolution": "Templates", "rawText": "raw"}, 201,
    ),
    (
        "patch", "PATCH", f"/ideas/{IDEA}", {"json": {"problem": "Edited"}}, True,
        "PATCH", f"/embed/ideas/{IDEA}", {}, {"problem": "Edited"}, 200,
    ),
    (
        "vote", "POST", f"/ideas/{IDEA}/vote", {"json": {"dir": "down"}}, False,
        "POST", f"/embed/ideas/{IDEA}/vote", {}, {"dir": "up"}, 200,
    ),
    (
        "status", "POST", f"/ideas/{IDEA}/status", {"json": {"toStatusId": "st-1"}}, True,
        "POST", f"/embed/ideas/{IDEA}/status", {}, {"toStatusId": "st-1"}, 200,
    ),
    (
        "reorder", "PUT", "/ideas/reorder", {"json": {"orderedIds": [IDEA, IDEA_B]}}, True,
        "PUT", "/embed/ideas/reorder", {}, {"orderedIds": [IDEA, IDEA_B]}, 200,
    ),
    (
        "merge", "POST", "/ideas/merge", {"json": {"survivorId": IDEA, "ideaIds": [IDEA_B]}}, True,
        "POST", "/embed/ideas/merge", {}, {"survivorId": IDEA, "ideaIds": [IDEA_B]}, 200,
    ),
    ("unmerge", "POST", f"/ideas/{IDEA}/unmerge", {}, True, "POST", f"/embed/ideas/{IDEA}/unmerge", {}, None, 200),
    (
        "promote", "POST", "/ideas/promote", {"json": {"ideaIds": [IDEA], "title": "Faster quotes"}}, True,
        "POST", "/embed/ideas/promote", {}, {"ideaIds": [IDEA], "title": "Faster quotes"}, 201,
    ),
    (
        "attach", "POST", f"/ideas/{IDEA}/attachments",
        {"files": {"file": ("brief.txt", b"hello zzt", "text/plain")}}, False,
        "POST", f"/embed/ideas/{IDEA}/attachments", {}, None, 201,
    ),
    (
        "content", "GET", f"/ideas/{IDEA}/attachments/{ATT}/content", {}, False,
        "GET", f"/embed/ideas/{IDEA}/attachments/{ATT}/content", {}, None, 200,
    ),
    ("comments-list", "GET", f"/ideas/{IDEA}/comments", {}, False, "GET", f"/embed/ideas/{IDEA}/comments", {}, None, 200),
    (
        "comments-post", "POST", f"/ideas/{IDEA}/comments", {"json": {"body": "Agreed", "parentId": None}}, False,
        "POST", f"/embed/ideas/{IDEA}/comments", {}, {"body": "Agreed", "parentId": None}, 201,
    ),
    (
        "comments-patch", "PATCH", f"/ideas/{IDEA}/comments/{COMMENT}", {"json": {"body": "Agreed, sorry"}}, False,
        "PATCH", f"/embed/ideas/{IDEA}/comments/{COMMENT}", {}, {"body": "Agreed, sorry"}, 200,
    ),
    (
        "comments-delete", "DELETE", f"/ideas/{IDEA}/comments/{COMMENT}", {}, False,
        "DELETE", f"/embed/ideas/{IDEA}/comments/{COMMENT}", {}, None, 204,
    ),
]
_ALL = [pytest.param(*r, id=r[0]) for r in _ROUTES]
_MANAGE_ONLY = [pytest.param(*r, id=r[0]) for r in _ROUTES if r[4]]
_VIEW_ONLY = [pytest.param(*r, id=r[0]) for r in _ROUTES if not r[4]]

_FIELDS = "name, method, path, kw, manage, ss_method, ss_path, ss_query, ss_json, ss_status"


def _script_ss(e: Env, ss_method: str, ss_path: str, ss_status: int) -> None:
    if ss_status == 204:
        e.fake.route(ss_method, ss_path, status=204)
    elif ss_path.endswith("/content"):
        e.fake.route(ss_method, ss_path, content=b"%PDF-1.4 zzt-bytes",
                     headers={"content-type": "application/pdf"})
    else:
        e.fake.route(ss_method, ss_path, status=ss_status, json_body={"id": IDEA, "ok": True})


@pytest.mark.parametrize(_FIELDS, _ALL)
def test_a08_route_forwards_to_the_right_ss_path(
    env, name, method, path, kw, manage, ss_method, ss_path, ss_query, ss_json, ss_status
):
    """AC-A-08: each CRM route forwards to its ss route (method, path, query, body) with the
    caller's embed token, and relays ss's status."""
    _script_ss(env, ss_method, ss_path, ss_status)
    resp = env.req(method, path, **kw)
    assert resp.status_code == ss_status, resp.text
    assert len(env.fake.calls) == 1, env.fake.calls
    call = env.fake.calls[0]
    assert (call["method"], call["path"]) == (ss_method, ss_path)
    for k, v in ss_query.items():
        assert call["query"].get(k) == v
    if ss_json is not None:
        assert call["json"] == ss_json
    assert call["headers"]["authorization"] == f"Bearer {env.fake.tokens[0]}"


@pytest.mark.parametrize(_FIELDS, _MANAGE_ONLY)
def test_a08_manage_routes_403_for_view_only_and_ss_not_called(
    env, name, method, path, kw, manage, ss_method, ss_path, ss_query, ss_json, ss_status
):
    env.allow.discard(MANAGE)
    resp = env.req(method, path, **kw)
    assert resp.status_code == 403, resp.text
    assert not _ss_called(env)


@pytest.mark.parametrize(_FIELDS, _VIEW_ONLY)
def test_a08_view_routes_work_for_view_only_user(
    env, name, method, path, kw, manage, ss_method, ss_path, ss_query, ss_json, ss_status
):
    env.allow.discard(MANAGE)
    _script_ss(env, ss_method, ss_path, ss_status)
    resp = env.req(method, path, **kw)
    assert resp.status_code == ss_status, resp.text
    assert len(env.fake.calls) == 1


@pytest.mark.parametrize(_FIELDS, _ALL)
def test_a01_user_without_view_gets_403_and_ss_never_called(
    env, name, method, path, kw, manage, ss_method, ss_path, ss_query, ss_json, ss_status
):
    env.allow.clear()
    resp = env.req(method, path, **kw)
    assert resp.status_code == 403, resp.text
    assert not _ss_called(env)


def test_a08_vote_always_posts_up_even_with_no_body(env):
    env.fake.route("POST", f"/embed/ideas/{IDEA}/vote", json_body={"id": IDEA})
    resp = env.req("POST", f"/ideas/{IDEA}/vote")
    assert resp.status_code == 200, resp.text
    assert env.fake.calls[0]["json"] == {"dir": "up"}


def test_a08_attachment_upload_is_forwarded_as_multipart(env):
    env.fake.route("POST", f"/embed/ideas/{IDEA}/attachments", status=201, json_body={"id": ATT})
    resp = env.req(
        "POST", f"/ideas/{IDEA}/attachments",
        files={"file": ("brief.txt", b"hello zzt", "text/plain")},
    )
    assert resp.status_code == 201, resp.text
    call = env.fake.calls[0]
    assert call["headers"]["content-type"].startswith("multipart/form-data")
    assert b'filename="brief.txt"' in call["content"]
    assert b"hello zzt" in call["content"]


def test_a08_attachment_content_is_streamed_back_unchanged(env):
    env.fake.route(
        "GET", f"/embed/ideas/{IDEA}/attachments/{ATT}/content",
        content=b"%PDF-1.4 zzt-bytes", headers={"content-type": "application/pdf"},
    )
    resp = env.req("GET", f"/ideas/{IDEA}/attachments/{ATT}/content")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 zzt-bytes"
    assert resp.headers["content-type"].startswith("application/pdf")


# --------------------------------------------------------------------------- #
# A-02 token minting and cache                                                 #
# --------------------------------------------------------------------------- #
def test_a02_assertion_is_minted_like_mint_embed_assertion_and_exchanged(env):
    env.req("GET", "/ideas")
    assert len(env.fake.session_calls) == 1
    sent = env.fake.session_calls[0]
    assert sent["connection_id"] == CONNECTION_ID
    claims = jwt.decode(
        sent["assertion"], SIGNING_SECRET, algorithms=[settings.jwt_algorithm], audience="ideation-embed"
    )
    assert claims["sub"] == env.user["id"]
    assert claims["email"] == env.user["email"]
    assert claims["connection_id"] == CONNECTION_ID
    assert claims["iss"] == "sorento" and claims["typ"] == "assertion"


def test_a02_second_call_inside_the_window_does_not_call_embed_session_again(env):
    env.req("GET", "/ideas")
    env.req("GET", "/ideas/board")
    assert len(env.fake.session_calls) == 1
    assert len(env.fake.calls) == 2
    assert {c["headers"]["authorization"] for c in env.fake.calls} == {f"Bearer {env.fake.tokens[0]}"}


def test_a02_token_inside_the_30s_margin_is_not_reused(env):
    env.fake.session_expires_in = 20  # < 30 s left: already stale on arrival
    env.req("GET", "/ideas")
    env.req("GET", "/ideas")
    assert len(env.fake.session_calls) == 2


def test_a02_token_is_cached_per_crm_user(env):
    env.req("GET", "/ideas")
    env.login(name="Bob Lim")
    env.req("GET", "/ideas")
    assert len(env.fake.session_calls) == 2
    assert env.fake.calls[0]["headers"]["authorization"] != env.fake.calls[1]["headers"]["authorization"]


def test_a02_service_get_embed_token_caches_and_force_refresh_remints(env):
    from app.services import ideation_gateway_service as gw

    user = env.user
    t1 = gw.get_embed_token(env.db, user)
    t2 = gw.get_embed_token(env.db, user)
    assert t1 == t2 == env.fake.tokens[0]
    assert len(env.fake.session_calls) == 1
    t3 = gw.get_embed_token(env.db, user, force_refresh=True)
    assert t3 == env.fake.tokens[1] != t1
    gw.clear_token_cache()
    gw.get_embed_token(env.db, user)
    assert len(env.fake.session_calls) == 3


def test_a02_service_raises_the_embed_errors_when_dormant_or_down(env, monkeypatch):
    import httpx

    from app.services import ideation_gateway_service as gw
    from app.services.ideation_embed_service import IdeationEmbedNotConfigured, IdeationEmbedUpstreamError

    env.fake.session_raises = httpx.ReadTimeout("slow")
    with pytest.raises(IdeationEmbedUpstreamError):
        gw.get_embed_token(env.db, env.login(name="Cy"), force_refresh=True)
    blank_embed_settings(monkeypatch)
    with pytest.raises(IdeationEmbedNotConfigured):
        gw.get_embed_token(env.db, env.login(name="Di"), force_refresh=True)


# --------------------------------------------------------------------------- #
# A-03 401 handling                                                            #
# --------------------------------------------------------------------------- #
def test_a03_ss_401_on_cached_token_remints_once_and_retries_once(env):
    assert env.req("GET", "/ideas").status_code == 200  # warm the cache
    env.fake.reject_next(1)
    resp = env.req("GET", "/ideas/board")
    assert resp.status_code == 200, resp.text
    assert len(env.fake.session_calls) == 2  # exactly one re-mint
    board_calls = [c for c in env.fake.calls if c["path"] == "/embed/board"]
    assert len(board_calls) == 2  # the 401 and exactly one retry
    assert board_calls[0]["headers"]["authorization"] == f"Bearer {env.fake.tokens[0]}"
    assert board_calls[1]["headers"]["authorization"] == f"Bearer {env.fake.tokens[1]}"


def test_a03_second_401_returns_502_and_drops_the_cache(env):
    env.req("GET", "/ideas")
    env.fake.reject_next(2)
    resp = env.req("GET", "/ideas/board")
    assert resp.status_code == 502, resp.text
    assert len([c for c in env.fake.calls if c["path"] == "/embed/board"]) == 2  # one retry, no more
    assert len(env.fake.session_calls) == 2
    # the poisoned entry is gone: the next request mints afresh and succeeds
    assert env.req("GET", "/ideas/board").status_code == 200
    assert len(env.fake.session_calls) == 3


# --------------------------------------------------------------------------- #
# A-04 the embed token never leaves the backend                                #
# --------------------------------------------------------------------------- #
def test_a04_token_never_in_a_response_body_or_header_or_log(env, caplog):
    caplog.set_level(logging.DEBUG)
    # ss answers carry nothing secret; any appearance of the token is the gateway's doing
    env.fake.route("GET", "/embed/ideas", json_body=[{"id": IDEA}])
    env.fake.route("GET", f"/embed/ideas/{IDEA}/attachments/{ATT}/content", content=b"bytes")
    responses = [
        env.req("GET", "/ideas"),
        env.req("GET", f"/ideas/{IDEA}"),
        env.req("GET", f"/ideas/{IDEA}/comments"),
        env.req("GET", f"/ideas/{IDEA}/attachments/{ATT}/content"),
        env.req("POST", f"/ideas/{IDEA}/vote"),
    ]
    env.fake.reject_next(2)
    responses.append(env.req("GET", "/ideas/board"))  # the 502 path too
    secrets = [*env.fake.tokens, SIGNING_SECRET] + [s["assertion"] for s in env.fake.session_calls]
    assert env.fake.tokens
    for r in responses:
        blob = r.text + " " + " ".join(f"{k}: {v}" for k, v in r.headers.items())
        for s in secrets:
            assert s not in blob
    for s in secrets:
        assert s not in caplog.text


# --------------------------------------------------------------------------- #
# A-05 outage and dormant                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("exc_name", ["ReadTimeout", "ConnectError", "ConnectTimeout"])
def test_a05_ss_timeout_or_down_on_a_call_is_502_with_the_friendly_message(env, exc_name):
    import httpx

    env.req("GET", "/ideas")  # warm, so the failure is on the data call
    env.fake.call_raises = getattr(httpx, exc_name)("boom")
    resp = env.req("GET", "/ideas/board")
    assert resp.status_code == 502, resp.text
    assert UNREACHABLE in message_of(resp)


def test_a05_ss_down_during_the_session_exchange_is_502_too(env):
    import httpx

    env.fake.session_raises = httpx.ReadTimeout("slow")
    resp = env.req("GET", "/ideas")
    assert resp.status_code == 502, resp.text
    assert UNREACHABLE in message_of(resp)


def test_a05_session_exchange_http_error_is_502(env):
    env.fake.session_status = 500
    resp = env.req("GET", "/ideas")
    assert resp.status_code == 502, resp.text
    assert UNREACHABLE in message_of(resp)


def test_a05_unconfigured_is_404_with_the_unavailable_message_and_no_ss_call(env, monkeypatch):
    blank_embed_settings(monkeypatch)
    resp = env.req("GET", "/ideas")
    assert resp.status_code == 404, resp.text
    assert UNAVAILABLE in message_of(resp)
    assert not _ss_called(env)


# --------------------------------------------------------------------------- #
# A-06 ss 4xx passthrough                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "status, ss_body, text",
    [
        (403, {"detail": "You do not have permission to promote ideas."}, "You do not have permission to promote ideas."),
        (403, {"error": {"code": "forbidden", "message": "You do not have permission to promote ideas."}},
         "You do not have permission to promote ideas."),
        (409, {"message": "That move isn't allowed."}, "That move isn't allowed."),
        (404, {"error": {"code": "not_found", "message": "Idea not found."}}, "Idea not found."),
    ],
    ids=["403-detail", "403-nested-error", "409-message", "404-nested-error"],
)
def test_a06_ss_4xx_is_passed_through_with_status_and_message(env, status, ss_body, text):
    env.fake.route("POST", "/embed/ideas/promote", status=status, json_body=ss_body)
    resp = env.req("POST", "/ideas/promote", json={"ideaIds": [IDEA], "title": "T"})
    assert resp.status_code == status, resp.text
    assert text in message_of(resp)


# --------------------------------------------------------------------------- #
# A-07 the name claim                                                          #
# --------------------------------------------------------------------------- #
def _name_claim(e: Env) -> str:
    e.req("GET", "/ideas")
    sent = e.fake.session_calls[-1]
    return jwt.decode(
        sent["assertion"], SIGNING_SECRET, algorithms=[settings.jwt_algorithm], audience="ideation-embed"
    )["name"]


def test_a07_name_claim_is_the_trimmed_users_name(env):
    env.login(name="  Alice Tan  ")
    assert _name_claim(env) == "Alice Tan"


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_a07_blank_name_becomes_sorento_staff_never_the_email(env, blank):
    user = env.login(name=blank, email="zzt-blank@example.test")
    claim = _name_claim(env)
    assert claim == "Sorento staff"
    assert claim != user["email"] and "@" not in claim


# --------------------------------------------------------------------------- #
# A-09 Archive and Delete as server-deferred pending actions                   #
# --------------------------------------------------------------------------- #
def test_a09_idea_actions_are_registered_record_actions():
    import app.services.record_actions  # noqa: F401  (registers)
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE, WINDOW_REVERSIBLE
    from app.services.form_action_registry import get_action

    delete, archive = get_action("idea.delete"), get_action("idea.archive")
    assert delete is not None and archive is not None
    for action in (delete, archive):
        assert action.entity_types == ("idea",)
        assert action.permission == MANAGE
    assert delete.window == WINDOW_DESTRUCTIVE  # 10 s hard delete
    assert archive.window == WINDOW_REVERSIBLE  # 5 s reversible


@pytest.mark.parametrize(
    "key, ss_method, ss_path_suffix, ss_json",
    [
        ("idea.delete", "DELETE", "", None),
        ("idea.archive", "POST", "/status", {"status": "archived"}),
    ],
)
def test_a09_handler_calls_ss_as_the_user_who_started_the_action(env, key, ss_method, ss_path_suffix, ss_json):
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    starter = env.login(name="Starter Sam")
    env.fake.route(ss_method, f"/embed/ideas/{IDEA}{ss_path_suffix}", status=204 if key == "idea.delete" else 200,
                   json_body=None if key == "idea.delete" else {"id": IDEA})
    get_action(key).execute(env.db, {"entity_id": IDEA, "requested_by_id": starter["id"]})

    assert len(env.fake.calls) == 1
    call = env.fake.calls[0]
    assert (call["method"], call["path"]) == (ss_method, f"/embed/ideas/{IDEA}{ss_path_suffix}")
    if ss_json is not None:
        assert call["json"] == ss_json
    claims = jwt.decode(
        env.fake.session_calls[-1]["assertion"], SIGNING_SECRET,
        algorithms=[settings.jwt_algorithm], audience="ideation-embed",
    )
    assert claims["sub"] == starter["id"]  # the starter, not whoever's request commits it
    assert claims["name"] == "Starter Sam"


@pytest.fixture
def pending(env):
    """The pending-actions route plus the commit sweep, scoped like the other record-action tests."""
    from fastapi import Depends

    from app.database import get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    def _scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[apply_company_scope] = _scope
    return env


def _lapse(db, action_id: str) -> None:
    from app.models.sla import SlaFormAction

    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    db.commit()


@pytest.mark.parametrize(
    "key, ss_method, ss_path_suffix",
    [("idea.delete", "DELETE", ""), ("idea.archive", "POST", "/status")],
)
def test_a09_ss_is_called_only_when_the_window_lapses(pending, key, ss_method, ss_path_suffix):
    from app.services.form_action_service import FormActionService

    e = pending
    e.fake.route(ss_method, f"/embed/ideas/{IDEA}{ss_path_suffix}", status=204 if key == "idea.delete" else 200,
                 json_body=None if key == "idea.delete" else {"id": IDEA})
    resp = e.client.post(
        "/api/v1/pending-actions",
        json={"action_key": key, "entity_type": "idea", "entity_id": IDEA, "payload": {}},
    )
    assert resp.status_code == 202, resp.text
    assert not e.fake.calls, "nothing may reach ss while the countdown runs"

    _lapse(e.db, resp.json()["id"])
    FormActionService(e.db).commit_due()
    assert [(c["method"], c["path"]) for c in e.fake.calls] == [(ss_method, f"/embed/ideas/{IDEA}{ss_path_suffix}")]


def test_a09_cancel_inside_the_window_means_ss_is_never_called(pending):
    from app.services.form_action_service import FormActionService

    e = pending
    resp = e.client.post(
        "/api/v1/pending-actions",
        json={"action_key": "idea.delete", "entity_type": "idea", "entity_id": IDEA, "payload": {}},
    )
    assert resp.status_code == 202, resp.text
    action_id = resp.json()["id"]
    cancel = e.client.post(f"/api/v1/pending-actions/{action_id}/cancel")
    assert cancel.status_code == 200, cancel.text

    _lapse(e.db, action_id)  # even if the clock runs out afterwards
    FormActionService(e.db).commit_due()
    assert not e.fake.calls and not e.fake.session_calls


def test_a09_view_only_user_cannot_park_a_delete(pending):
    e = pending
    e.allow.discard(MANAGE)
    resp = e.client.post(
        "/api/v1/pending-actions",
        json={"action_key": "idea.delete", "entity_type": "idea", "entity_id": IDEA, "payload": {}},
    )
    assert resp.status_code == 403, resp.text
    assert not e.fake.calls


# --------------------------------------------------------------------------- #
# E-03 comment delete is a server-deferred countdown too                        #
# --------------------------------------------------------------------------- #
def test_e03_comment_delete_is_a_registered_record_action_open_to_any_viewer():
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE
    from app.services.form_action_registry import get_action

    action = get_action("idea_comment.delete")
    assert action is not None
    assert action.entity_types == ("idea_comment",)
    assert action.permission == VIEW  # ss enforces own-or-moderator; the CRM does not widen it
    assert action.window == WINDOW_DESTRUCTIVE


def test_e03_comment_delete_handler_calls_ss_as_the_requester(env):
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    starter = env.login(name="Starter Sam")
    env.fake.route("DELETE", f"/embed/ideas/{IDEA}/comments/{COMMENT}", status=204)
    get_action("idea_comment.delete").execute(
        env.db, {"entity_id": COMMENT, "idea_id": IDEA, "requested_by_id": starter["id"]}
    )
    assert [(c["method"], c["path"]) for c in env.fake.calls] == [("DELETE", f"/embed/ideas/{IDEA}/comments/{COMMENT}")]
    claims = jwt.decode(
        env.fake.session_calls[-1]["assertion"], SIGNING_SECRET,
        algorithms=[settings.jwt_algorithm], audience="ideation-embed",
    )
    assert claims["sub"] == starter["id"]


def test_e03_comment_delete_is_not_sent_to_ss_until_the_window_lapses(pending):
    from app.services.form_action_service import FormActionService

    e = pending
    e.fake.route("DELETE", f"/embed/ideas/{IDEA}/comments/{COMMENT}", status=204)
    resp = e.client.post(
        "/api/v1/pending-actions",
        json={"action_key": "idea_comment.delete", "entity_type": "idea_comment", "entity_id": COMMENT,
              "payload": {"idea_id": IDEA}},
    )
    assert resp.status_code == 202, resp.text
    assert not e.fake.calls
    _lapse(e.db, resp.json()["id"])
    FormActionService(e.db).commit_due()
    assert [(c["method"], c["path"]) for c in e.fake.calls] == [("DELETE", f"/embed/ideas/{IDEA}/comments/{COMMENT}")]
