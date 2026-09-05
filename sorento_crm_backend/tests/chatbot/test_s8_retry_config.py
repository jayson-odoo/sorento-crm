"""S8a retry ingress config (AC-804): the retry webhook URL and key move off the
environment onto the default respond workspace row, Fernet-encrypted the same way
`ideation_intake_api_key_ciphertext` already is on that model
(`app/models/respond_workspace.py`, `app/services/respond_workspace_service.py`),
admin-editable under `user_management.settings.edit`, write-only (a GET never echoes
the key), validated against SSRF (loopback / private range / the CRM's own host) on
BOTH save and use, and sent with the key header and redirects disabled.

RED-first: none of this exists yet. Every test here is expected to fail for one of:
  - AttributeError (a model column or schema field that does not exist yet);
  - an assertion mismatch (a value today's code does not produce, e.g. a masked
    string where a bool is required, or a 403 from the wrong permission);
  - a 409 where a 422 is required (URL validation not wired at all yet).
None of these is an import error in this file itself - if pytest reports one, that
is a fixture bug in this file, not the expected shape of red.

ASSUMPTIONS, flagged for the coder rather than settled unilaterally (mirrors the
style of `tests/chatbot/test_turns_admin_api.py`'s own docstring):

1. The GET/response field for "is a key stored" is `has_chatbot_retry_key: bool`
   (the plan's own words) - NOT a `_masked` string like the sibling ideation
   fields. This is the one respond-workspace secret the UI must never render even
   a last-4 hint of, because it authorises injecting a message back into a real
   customer's WhatsApp conversation.
2. `PUT /respond-workspaces/{id}` is the SAME route the other workspace fields use,
   widened so granting ONLY `user_management.settings.edit` (no
   `system.respond_workspaces.edit`) is sufficient to write the two chatbot-retry
   fields. Permission is stubbed at both `UserPermissionService.
   check_user_has_permission` (`require_permission`) AND
   `get_user_permission_slugs` / `get_user_role_slugs` (`require_any_permission`),
   so whichever the coder picks, granting exactly this one slug is enough.
3. `app.services.chatbot.dispatch.reinject_envelope` (and its `ingress_url` /
   `retry_available` seams) read the DEFAULT respond workspace row instead of
   `settings.chatbot_retry_ingress_url` / `_key`. The retry endpoint tests seed a
   default `RespondWorkspace` row rather than monkeypatching `settings`.
4. The SSRF validator resolves hostnames via `socket.getaddrinfo` (patched here)
   and decides "the CRM's own host" by comparing against `socket.gethostname()`
   (also patched, to the SAME hostname the candidate URL uses) - this works
   whichever comparison strategy (hostname string, or the IP both resolve to) the
   validator ends up using.
"""
from __future__ import annotations

import socket
import uuid
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.chatbot_turn import ChatbotTurn
from app.models.respond_workspace import RespondWorkspace
from app.schemas.respond_workspace import RespondWorkspaceCreate, RespondWorkspaceUpdate
from app.services.respond_workspace_service import RespondWorkspaceService
from app.services.user_service import UserPermissionService
from app.utils.field_encryption import decrypt_secret
from tests._pg_fixture import blank_session

VALID_RETRY_URL = "https://automate-sorento.foundryx.my/webhook/sorento-main-inject"
PLAIN_RETRY_KEY = "ZZT-plain-retry-key-99"

EDIT_SLUG = "user_management.settings.edit"

TURNS_BASE = "/api/v1/system/chatbot/turns"
WORKSPACES_BASE = "/api/v1/system/respond-workspaces"


def _resolve_ok(host: str, ip: str):
    """A `socket.getaddrinfo`-shaped result for a hostname that resolves to `ip`."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))]


# --------------------------------------------------------------------------- #
# 1. Model + service: the two new columns, encrypted like the ideation key.   #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def session():
    with blank_session() as s:
        yield s


class TestModelAndServiceEncryption:
    def test_model_has_the_two_new_columns(self, session):
        row = RespondWorkspace(
            space_id="ZZT-space-804",
            api_key_ciphertext="irrelevant-for-this-test",
        )
        # AttributeError today: `chatbot_retry_ingress_url` /
        # `chatbot_retry_ingress_key_ciphertext` are not declared on the model.
        row.chatbot_retry_ingress_url = VALID_RETRY_URL
        row.chatbot_retry_ingress_key_ciphertext = "whatever-the-encrypted-form-is"
        session.add(row)
        session.commit()

        # A plain instance attribute survives `refresh()` untouched even when it is
        # NOT a mapped column (refresh only reloads mapped attributes), which would
        # make this test pass for the wrong reason. Querying through the CLASS-level
        # attribute forces SQLAlchemy to resolve it as a real mapped column - today
        # that raises AttributeError, which is the right red.
        reread = (
            session.query(RespondWorkspace)
            .filter(RespondWorkspace.chatbot_retry_ingress_url == VALID_RETRY_URL)
            .first()
        )
        assert reread is not None
        assert reread.chatbot_retry_ingress_key_ciphertext == "whatever-the-encrypted-form-is"

    def test_service_update_stores_the_key_fernet_encrypted(self, session):
        svc = RespondWorkspaceService(session)
        row = svc.create(
            RespondWorkspaceCreate(space_id="ZZT-space-804b", api_key="k", is_default=True)
        )
        payload = RespondWorkspaceUpdate(
            chatbot_retry_ingress_url=VALID_RETRY_URL,
            chatbot_retry_ingress_key=PLAIN_RETRY_KEY,
        )
        # Today's `RespondWorkspaceUpdate` silently drops unknown fields (Pydantic
        # v2 default `extra="ignore"`), so this is the FIRST failure a red run
        # should show: not an exception, an assertion that the schema does not
        # carry the field at all yet.
        assert hasattr(payload, "chatbot_retry_ingress_url"), (
            "RespondWorkspaceUpdate has no chatbot_retry_ingress_url field yet"
        )
        assert hasattr(payload, "chatbot_retry_ingress_key"), (
            "RespondWorkspaceUpdate has no chatbot_retry_ingress_key field yet"
        )

        updated = svc.update(row.id, payload)

        assert updated.chatbot_retry_ingress_url == VALID_RETRY_URL
        ciphertext = updated.chatbot_retry_ingress_key_ciphertext
        assert ciphertext, "the key was not stored at all"
        assert ciphertext != PLAIN_RETRY_KEY, (
            "the retry key was stored in PLAINTEXT - it must be Fernet-encrypted "
            "the same way ideation_intake_api_key_ciphertext is"
        )
        assert decrypt_secret(ciphertext) == PLAIN_RETRY_KEY

    def test_response_dict_never_echoes_the_key_only_a_bool(self, session):
        svc = RespondWorkspaceService(session)
        row = svc.create(
            RespondWorkspaceCreate(space_id="ZZT-space-804c", api_key="k", is_default=True)
        )
        # Before any key is set: no key configured.
        before = svc.to_response_dict(row)
        assert before.get("has_chatbot_retry_key") is False
        assert "chatbot_retry_ingress_key" not in before
        assert "chatbot_retry_ingress_key_ciphertext" not in before
        assert "chatbot_retry_ingress_key_masked" not in before, (
            "AC-804: this secret is never echoed, not even as a last-4 masked hint "
            "the way the sibling ideation fields are - it authorises a real "
            "customer-facing send"
        )

        updated = svc.update(
            row.id,
            RespondWorkspaceUpdate(
                chatbot_retry_ingress_url=VALID_RETRY_URL,
                chatbot_retry_ingress_key=PLAIN_RETRY_KEY,
            ),
        )
        after = svc.to_response_dict(updated)
        assert after.get("has_chatbot_retry_key") is True
        assert PLAIN_RETRY_KEY not in str(after)
        assert after.get("chatbot_retry_ingress_url") == VALID_RETRY_URL


# --------------------------------------------------------------------------- #
# 2. Admin route: permission + save-time validation.                         #
# --------------------------------------------------------------------------- #

_GRANTS: set[str] = set()
_ACTOR: dict[str, Any] = {"id": None, "name": "ZZT S8a Tester"}


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    _GRANTS.clear()
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in _GRANTS,
    )
    monkeypatch.setattr(
        UserPermissionService, "get_user_permission_slugs", lambda self, uid: set(_GRANTS)
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTS.clear()


@pytest.fixture()
def client(session):
    def _override_db():
        try:
            yield session
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
def default_workspace(session) -> RespondWorkspace:
    svc = RespondWorkspaceService(session)
    return svc.create(
        RespondWorkspaceCreate(space_id="ZZT-space-804-default", api_key="k", is_default=True)
    )


class TestUpdateRoutePermission:
    def test_settings_edit_alone_is_sufficient(self, client, default_workspace):
        """AC-804: 'editable ... under user_management.settings.edit'. A caller with
        ONLY this slug - no system.respond_workspaces.edit at all - must be able to
        save the two chatbot-retry fields. Today only system.respond_workspaces.edit
        is checked, so this 403s."""
        _GRANTS.add(EDIT_SLUG)
        resp = client.put(
            f"{WORKSPACES_BASE}/{default_workspace.id}",
            json={
                "chatbot_retry_ingress_url": VALID_RETRY_URL,
                "chatbot_retry_ingress_key": PLAIN_RETRY_KEY,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("has_chatbot_retry_key") is True

    def test_no_grant_at_all_is_denied(self, client, default_workspace):
        resp = client.put(
            f"{WORKSPACES_BASE}/{default_workspace.id}",
            json={"chatbot_retry_ingress_url": VALID_RETRY_URL},
        )
        assert resp.status_code == 403, resp.text


class TestUrlValidationOnSave:
    """Rejected on save: not-https, loopback, private range, link-local/metadata,
    and the CRM's own host - each a 422 naming the rule."""

    @pytest.mark.parametrize(
        "url,keywords",
        [
            ("http://automate-sorento.foundryx.my/webhook/x", ("https",)),
            ("https://localhost/webhook/x", ("loopback", "localhost")),
            ("https://127.0.0.1/webhook/x", ("loopback",)),
            ("https://10.0.0.1/webhook/x", ("private",)),
            ("https://169.254.169.254/webhook/x", ("link-local", "metadata", "private")),
            ("https://[::1]/webhook/x", ("loopback",)),
            # S8a review B1: an IPv6 literal that CARRIES an IPv4 address. The mapped
            # form (`::ffff:a.b.c.d`) used to skip the private-range test entirely - an
            # IPv6Address is never `in` an IPv4Network, so membership answered False on
            # a version mismatch - and `https://[::ffff:10.0.0.1]/` was accepted while
            # `https://10.0.0.1/` was refused. Loopback and link-local happened to be
            # caught anyway (CPython delegates those two properties to the mapped v4),
            # which is why only the range cases leaked; all four are pinned so the
            # normalisation cannot regress for one family and not the other.
            ("https://[::ffff:10.0.0.1]/hook", ("private",)),
            ("https://[::ffff:127.0.0.1]/hook", ("loopback",)),
            ("https://[::ffff:169.254.169.254]/hook", ("link-local", "metadata")),
            ("https://[::ffff:100.64.0.1]/hook", ("private",)),
            # 6to4 and Teredo TUNNEL to the v4 address they encode, so a public-looking
            # v6 literal reaches 127.0.0.1 / 10.0.0.1 anyway.
            ("https://[2002:7f00:1::]/hook", ("loopback",)),
            ("https://[2001:0:c000:0201:0:0:f5ff:fffe]/hook", ("private",)),
            # S8a review N4: userinfo would be stored in clear on the workspace row.
            (
                "https://admin:hunter2@automate-sorento.foundryx.my/webhook/x",
                ("username", "password"),
            ),
        ],
    )
    def test_rejected_urls_422_name_the_rule(
        self, client, default_workspace, monkeypatch, url, keywords
    ):
        _GRANTS.add(EDIT_SLUG)
        resp = client.put(
            f"{WORKSPACES_BASE}/{default_workspace.id}",
            json={"chatbot_retry_ingress_url": url},
        )
        assert resp.status_code == 422, (
            f"expected 422 for {url!r}, got {resp.status_code}: {resp.text}"
        )
        text = resp.text.lower()
        assert any(kw in text for kw in keywords), (
            f"422 body does not name the rule (expected one of {keywords}): {resp.text}"
        )

    def test_a_hostname_that_resolves_to_the_crm_itself_is_rejected(
        self, client, default_workspace, monkeypatch
    ):
        own_host = "sorento-crm-api.internal"
        own_ip = "203.0.113.50"  # TEST-NET-3 (RFC 5737): public-looking, not private/loopback

        def fake_getaddrinfo(host, *args, **kwargs):
            if host in (own_host, socket.gethostname()):
                return _resolve_ok(host, own_ip)
            return _resolve_ok(host, "198.51.100.7")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(socket, "gethostname", lambda: own_host)

        _GRANTS.add(EDIT_SLUG)
        resp = client.put(
            f"{WORKSPACES_BASE}/{default_workspace.id}",
            json={"chatbot_retry_ingress_url": f"https://{own_host}/webhook/x"},
        )
        assert resp.status_code == 422, resp.text
        text = resp.text.lower()
        assert any(kw in text for kw in ("itself", "own host", "self", "crm")), (
            f"422 body does not name the 'resolves to the CRM itself' rule: {resp.text}"
        )

    def test_a_normal_public_webhook_host_is_accepted(
        self, client, default_workspace, monkeypatch
    ):
        """The happy path for save-time validation: a real n8n webhook host,
        resolved (via the patched getaddrinfo) to an ordinary public IP."""
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, *a, **kw: _resolve_ok(host, "198.51.100.7"),
        )
        monkeypatch.setattr(socket, "gethostname", lambda: "some-other-host")

        _GRANTS.add(EDIT_SLUG)
        resp = client.put(
            f"{WORKSPACES_BASE}/{default_workspace.id}",
            json={"chatbot_retry_ingress_url": VALID_RETRY_URL},
        )
        assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# 3. Retry endpoint: reads the workspace, not settings; 409 with no URL;      #
#    422 on a URL that is bad at USE time; key header + no redirects on send. #
# --------------------------------------------------------------------------- #


def _seed_turn(session, *, contact_respond_id: str) -> ChatbotTurn:
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_respond_id,
        message_id=f"ZZT-msg-{uuid.uuid4().hex[:8]}",
        ingress="webhook",
        envelope={
            "message": {"messageId": "ZZT-msg-1", "message": {"type": "text", "text": "hi"}},
            "contact": {"id": contact_respond_id},
        },
        status="failed",
        stage="understood",
        error="parser timed out",
        attempt=1,
        trace=[],
    )
    session.add(turn)
    session.commit()
    return turn


class TestRetryReadsTheWorkspaceRow:
    def test_no_url_on_the_default_workspace_is_409_no_outbound_call(
        self, client, session, default_workspace, monkeypatch
    ):
        _GRANTS.add("system.chat_history.manage")
        # default_workspace has NO chatbot_retry_ingress_url set at all.
        mock_post = MagicMock()
        monkeypatch.setattr(httpx, "post", mock_post)

        turn = _seed_turn(session, contact_respond_id="ZZT-contact-804-nourl")
        resp = client.post(f"{TURNS_BASE}/{turn.id}/retry")
        assert resp.status_code == 409, resp.text
        mock_post.assert_not_called()

    def test_valid_url_and_key_sends_header_with_redirects_disabled(
        self, client, session, default_workspace, monkeypatch
    ):
        _GRANTS.add("system.chat_history.manage")
        svc = RespondWorkspaceService(session)
        svc.update(
            default_workspace.id,
            RespondWorkspaceUpdate(
                chatbot_retry_ingress_url=VALID_RETRY_URL,
                chatbot_retry_ingress_key=PLAIN_RETRY_KEY,
            ),
        )
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda host, *a, **kw: _resolve_ok(host, "198.51.100.7")
        )
        monkeypatch.setattr(socket, "gethostname", lambda: "some-other-host")

        mock_post = MagicMock(
            return_value=httpx.Response(200, request=httpx.Request("POST", VALID_RETRY_URL))
        )
        monkeypatch.setattr(httpx, "post", mock_post)

        turn = _seed_turn(session, contact_respond_id="ZZT-contact-804-valid")
        resp = client.post(f"{TURNS_BASE}/{turn.id}/retry")
        assert resp.status_code == 200, resp.text

        mock_post.assert_called_once()
        call = mock_post.call_args
        called_url = call.args[0] if call.args else call.kwargs.get("url")
        assert called_url == VALID_RETRY_URL
        headers = call.kwargs.get("headers") or {}
        assert headers.get("X-Chatbot-Retry-Key") == PLAIN_RETRY_KEY
        assert call.kwargs.get("follow_redirects") is False, (
            "the retry POST must explicitly disable redirects, not rely on the "
            "library default"
        )

    def test_a_url_that_is_bad_at_use_time_is_422_not_409(
        self, client, session, default_workspace, monkeypatch
    ):
        """Defense in depth (AC-804: 'when saved or used'): a row whose URL was
        written directly (bypassing the save-time check, e.g. by an older row, or a
        DNS answer that changed after save) must still be refused when Retry is
        pressed - and refused as a VALIDATION failure (422), not the "nothing
        configured" case (409)."""
        _GRANTS.add("system.chat_history.manage")
        default_workspace.chatbot_retry_ingress_url = "https://127.0.0.1/webhook/x"
        session.add(default_workspace)
        session.commit()

        mock_post = MagicMock()
        monkeypatch.setattr(httpx, "post", mock_post)

        turn = _seed_turn(session, contact_respond_id="ZZT-contact-804-bad-at-use")
        resp = client.post(f"{TURNS_BASE}/{turn.id}/retry")
        assert resp.status_code == 422, resp.text
        assert "loopback" in resp.text.lower()
        mock_post.assert_not_called()


# --------------------------------------------------------------------------- #
# 4. Guardrail: the env-based config is gone from config.py / .env.example.  #
# --------------------------------------------------------------------------- #


def test_env_based_retry_config_is_gone_from_config_and_env_example():
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[2]
    config_source = (backend_root / "app" / "config.py").read_text(encoding="utf-8")
    assert "chatbot_retry_ingress" not in config_source.lower(), (
        "CHATBOT_RETRY_INGRESS_URL / _KEY must be deleted from app/config.py - the "
        "config now lives on the respond workspace row (AC-804)"
    )

    for candidate in (
        backend_root / ".env.example",
        backend_root.parent / "sorento_crm_backend" / ".env.example",
    ):
        if candidate.is_file():
            assert "chatbot_retry_ingress" not in candidate.read_text(encoding="utf-8").lower()
