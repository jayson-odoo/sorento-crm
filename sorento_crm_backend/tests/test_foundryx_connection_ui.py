"""RED tests for SR6 of the AutoCount pull + review lane (issue #1077).

Plan: documentation/plans/autocount/PLAN-foundryx-pull-connection-ui.md
UAC:  documentation/plans/autocount/foundryx-pull-connection-ui-acceptance-criteria.md

Nothing under test exists yet:

* ``FoundryxAutocountClient.__init__`` still takes no arguments and reads
  ``settings.foundryx_base_url`` / ``foundryx_api_key`` - calling
  ``FoundryxAutocountClient(db)`` raises ``TypeError`` today. That IS the correct red
  for every ``TestConnectionResolution`` test.
* ``settings`` still carries the two FoundryX attributes, so the ``hasattr`` assertion
  in AC-CN-4 fails today (not an error - a real, wrong, answer).
* ``POST /api/v1/integrations/manage/{id}/test`` does not exist - every
  ``TestConnectionTestRoute`` test gets a 404 today, regardless of the scenario it
  sets up. That is the correct red for every one of them.

The two-session AC-CN-5 test needs TWO ``Session`` objects that see each other's
writes without ever truly committing to Postgres (so the outer rollback still leaves
nothing behind) - the same ``task_db``-style rig ``test_autocount_pull_sr1.py`` proved
out: one connection, ``sessionmaker(..., join_transaction_mode="create_savepoint")``,
two ``Session()`` instances bound to it.

FoundryX's contract update (2026-09-21, relayed by the captain, already folded into
the plan/UAC in this worktree): gateway 403 means FoundryX's own service is off
("AutoCount service is not enabled on FoundryX", not a per-company key restriction),
and a new 429 case ("Too many attempts, try again shortly") sits alongside it.
"""
from __future__ import annotations

import logging
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards (repo convention, see test_autocount_pull_sr1.py).
from app.main import app  # noqa: E402

import tests.support.fake_foundryx as fake_foundryx
from tests._pg_fixture import _BLANK, blank_schema_engine, blank_session

MARKER = "ZZTCN"
NIL_SNAPSHOT = "00000000-0000-0000-0000-000000000000"
FAKE_BASE_URL = "http://foundryx.fake"


def _test_route(integration_id: str) -> str:
    # The real mount (app/api/v1/__init__.py): prefix "/integrations/manage", NOT the
    # plan prose's shorthand "/api/v1/integrations/{id}/test".
    return f"/api/v1/integrations/manage/{integration_id}/test"


# ============================================================ transport helpers


def _forwarding_handler(fake_client: TestClient):
    """An ``httpx.MockTransport`` handler that forwards to a real ``TestClient`` app -
    the same no-real-socket trick ``test_fake_foundryx.py``'s last test uses, so this
    file never needs an actual bound port for the fake gateway."""

    def handler(request: httpx.Request) -> httpx.Response:
        response = fake_client.request(
            request.method,
            request.url.path,
            params=dict(request.url.params),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(response.status_code, content=response.content)

    return handler


def _canned_json_handler(status_code: int, body: dict):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    return handler


def _canned_html_handler(status_code: int):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=b"<html><body>404 not found</body></html>",
            headers={"content-type": "text/html"},
        )

    return handler


def _patch_transport(monkeypatch, handler) -> None:
    import app.services.foundryx_autocount_client as client_mod

    monkeypatch.setattr(
        client_mod, "TRANSPORT", httpx.MockTransport(handler) if handler else None, raising=False
    )


def _no_call_allowed_handler():
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("FoundryxAutocountClient must not call the gateway when NOT_CONFIGURED")

    return handler


# ==================================================================== fixtures


@pytest.fixture
def two_sessions():
    """Two ``Session`` objects on ONE connection over the shared blank schema.

    Mirrors ``test_autocount_pull_sr1.py``'s ``task_db`` fixture: proven empirically
    that two ``Session`` objects sharing a connection under
    ``join_transaction_mode="create_savepoint"`` see each other's commits, and that
    nothing survives once the outer transaction rolls back at teardown.
    """
    engine = blank_schema_engine()
    connection = engine.connect()
    transaction = connection.begin()
    name = _BLANK["name"]
    connection.exec_driver_sql(
        f'SET LOCAL search_path TO "{name}", "{name}_scm", "{name}_dealer_kit", '
        f'"{name}_chatbot", "{name}_projects"'
    )
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    s1, s2 = factory(), factory()
    try:
        yield s1, s2
    finally:
        # Sharing one connection means every autobegin stacks ONE savepoint chain
        # regardless of which Session issued it - s2's post-commit SELECT autobegins
        # a savepoint on top of whatever s1 last left open. Closing s1 first rolls
        # back to ITS savepoint and destroys s2's from under it, so s2.close() then
        # tries to roll back to a savepoint that no longer exists and raises
        # InvalidSavepointSpecification. Closing in reverse order of last use avoids
        # that, and each close is guarded so one Session's teardown error can never
        # skip the connection/transaction cleanup below - an unguarded exception here
        # previously left an aborted connection holding the schema's lock, hanging
        # the next test and the session-end DROP SCHEMA.
        for s in (s2, s1):
            try:
                s.close()
            except Exception:
                pass
        try:
            transaction.rollback()
        finally:
            connection.close()


def _make_user(db, *perm_slugs: str) -> dict:
    """A user holding EXACTLY the given permission slugs - never superadmin."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    uid = str(uuid.uuid4())
    role_id = str(uuid.uuid4())
    db.add(
        UserRole(
            id=role_id,
            slug=f"{MARKER.lower()}-role-{uid[:8]}",
            name=f"{MARKER} role {uid[:8]}",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=uid, email=f"{MARKER.lower()}-{uid[:8]}@test.com", name="U", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
    for slug in perm_slugs:
        perm = db.query(UserPermission).filter_by(slug=slug).one_or_none()
        if perm is None:
            perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=perm.id))
    db.commit()
    return {"id": uid, "email": f"{MARKER.lower()}-{uid[:8]}@test.com"}


class _RouteEnv:
    def __init__(self, db):
        self.db = db
        self.client: TestClient | None = None
        self._principal: dict | None = None

    def as_user(self, principal: dict) -> None:
        self._principal = principal

    def principal(self) -> dict:
        assert self._principal is not None, "call env.as_user(...) before making a request"
        return self._principal

    def post_test(self, integration_id: str):
        return self.client.post(_test_route(integration_id))


@pytest.fixture
def route_env():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db

    with blank_session() as db:
        env = _RouteEnv(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: env.principal()
        app.dependency_overrides[get_current_user_or_api_key] = lambda: env.principal()

        env.client = TestClient(app)
        try:
            yield env
        finally:
            app.dependency_overrides.clear()


def _seed_non_esb_integration(db):
    from app.services.integration_admin_service import IntegrationAdminService

    return IntegrationAdminService(db).create(
        name=f"{MARKER.lower()}-n8n-{uuid.uuid4().hex[:8]}",
        type_="automation",
        config_json=None,
        credentials_json=None,
        is_active=True,
    )


# =============================================================================
# TestConnectionResolution - AC-CN-1, CN-2, CN-3, CN-4, CN-5, CN-7
# =============================================================================


class TestConnectionResolution:
    def test_ac_cn_1_builds_from_the_row_and_sends_the_key_to_that_base_url(self, monkeypatch):
        """A row with base_url + credentials builds a client whose calls carry the
        decrypted key in X-API-Key and go to that base_url."""
        from app.services.foundryx_autocount_client import FoundryxAutocountClient

        api_key = "fxa_test_cn1_secret"
        fake_client = TestClient(fake_foundryx.app)
        _patch_transport(monkeypatch, _forwarding_handler(fake_client))

        with blank_session() as db:
            fake_foundryx.seed_foundryx_connection(db, base_url=FAKE_BASE_URL, api_key=api_key)
            db.commit()

            client = FoundryxAutocountClient(db)
            assert client._base_url == FAKE_BASE_URL

            # "build" is what a pull start actually calls - a 2xx path, unlike
            # status()/rows_page() on an unknown id, which the client's own _parse
            # maps to NOT_CONFIGURED (401/403/404 all mean "bad key" for those calls;
            # that mapping is unchanged by SR6).
            body = client.build(f"{MARKER}CO", "products")

        assert body["status"] == "building"
        assert fake_foundryx.LAST_API_KEY == api_key

    def test_ac_cn_2_no_row_raises_not_configured_before_any_http_call(self, monkeypatch):
        from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError

        _patch_transport(monkeypatch, _no_call_allowed_handler())

        with blank_session() as db:
            with pytest.raises(FoundryxPullError) as excinfo:
                FoundryxAutocountClient(db)

        assert excinfo.value.code == "NOT_CONFIGURED"
        assert excinfo.value.status == 503

    @pytest.mark.parametrize(
        "shape",
        ["inactive", "blank_base_url", "no_credentials", "credentials_without_api_key"],
    )
    def test_ac_cn_3_row_present_but_unusable_raises_not_configured(self, monkeypatch, shape):
        from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError

        _patch_transport(monkeypatch, _no_call_allowed_handler())

        with blank_session() as db:
            if shape == "inactive":
                fake_foundryx.seed_foundryx_connection(
                    db, base_url=FAKE_BASE_URL, api_key="k", active=False
                )
            elif shape == "blank_base_url":
                fake_foundryx.seed_foundryx_connection(db, base_url="", api_key="k")
            elif shape == "no_credentials":
                row = fake_foundryx.seed_foundryx_connection(db, base_url=FAKE_BASE_URL, api_key="k")
                row.credentials_json = None
                db.flush()
            elif shape == "credentials_without_api_key":
                row = fake_foundryx.seed_foundryx_connection(db, base_url=FAKE_BASE_URL, api_key="k")
                from app.services.integration_admin_service import IntegrationAdminService

                IntegrationAdminService(db).update(row, credentials_json={"not_api_key": "x"})
            db.commit()

            with pytest.raises(FoundryxPullError) as excinfo:
                FoundryxAutocountClient(db)

        assert excinfo.value.code == "NOT_CONFIGURED"
        assert excinfo.value.status == 503

    def test_ac_cn_4_settings_no_longer_carries_foundryx_env(self):
        from app.config import settings

        assert not hasattr(settings, "foundryx_base_url")
        assert not hasattr(settings, "foundryx_api_key")

    def test_ac_cn_5_a_key_rotated_in_the_row_is_used_by_the_very_next_build(self, two_sessions):
        """Two Session objects, one connection (see fixture docstring): the second
        build sees the rotated key with no shared client cache and no restart."""
        from app.services.foundryx_autocount_client import FoundryxAutocountClient
        from app.services.integration_admin_service import IntegrationAdminService
        from app.models.integration import Integration

        s1, s2 = two_sessions
        fake_foundryx.seed_foundryx_connection(s1, base_url=FAKE_BASE_URL, api_key="key-A")
        s1.commit()

        client1 = FoundryxAutocountClient(s1)
        assert client1._api_key == "key-A"

        row = s2.query(Integration).filter_by(name="foundryx-esb").one()
        IntegrationAdminService(s2).update(row, credentials_json={"api_key": "key-B"})
        s2.commit()

        client2 = FoundryxAutocountClient(s2)
        assert client2._api_key == "key-B"
        # The client built before rotation is unaffected - proves there is no
        # process-wide cache a restart would otherwise be needed to clear.
        assert client1._api_key == "key-A"

    def test_ac_cn_7_the_key_never_appears_in_a_log_line_during_a_pull_start(
        self, monkeypatch, caplog
    ):
        from app.services.foundryx_autocount_client import FoundryxAutocountClient

        api_key = "fxa_should_never_appear_in_any_log_line"
        fake_client = TestClient(fake_foundryx.app)
        _patch_transport(monkeypatch, _forwarding_handler(fake_client))
        caplog.set_level(logging.DEBUG)

        with blank_session() as db:
            fake_foundryx.seed_foundryx_connection(db, base_url=FAKE_BASE_URL, api_key=api_key)
            db.commit()

            client = FoundryxAutocountClient(db)
            client.build(f"{MARKER}CO7", "products")  # "a pull start"

        for record in caplog.records:
            assert api_key not in record.getMessage()


# =============================================================================
# TestConnectionTestRoute - AC-TS-1 .. AC-TS-9
# =============================================================================


class TestConnectionTestRoute:
    def test_ac_ts_1_json_404_unknown_snapshot_means_connected(self, monkeypatch, route_env):
        fake_client = TestClient(fake_foundryx.app)
        _patch_transport(monkeypatch, _forwarding_handler(fake_client))

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts1"
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["message"] == "Connected"
        assert isinstance(body["latency_ms"], int)

    def test_ac_ts_2_401_means_key_rejected(self, monkeypatch, route_env):
        _patch_transport(
            monkeypatch,
            _canned_json_handler(
                401, {"code": "INVALID_API_KEY", "message": "Missing, malformed, unknown or revoked key."}
            ),
        )

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts2"
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["message"] == "Key rejected"

    def test_ac_ts_3_403_means_service_not_enabled_on_foundryx(self, monkeypatch, route_env):
        # FoundryX contract update 2026-09-21: 403 is THEIR service being off, not a
        # per-company key restriction.
        _patch_transport(
            monkeypatch,
            _canned_json_handler(
                403, {"code": "SERVICE_NOT_ENABLED", "message": "Service disabled."}
            ),
        )

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts3"
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["message"] == "AutoCount service is not enabled on FoundryX"

    def test_ac_ts_3b_429_means_too_many_attempts(self, monkeypatch, route_env):
        # New case from the same 2026-09-21 contract update.
        _patch_transport(
            monkeypatch,
            _canned_json_handler(
                429, {"code": "TOO_MANY_REQUESTS", "message": "Rate limited."}
            ),
        )

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts3b"
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["message"] == "Too many attempts, try again shortly"

    def test_ac_ts_4_non_json_404_means_not_a_foundryx_gateway(self, monkeypatch, route_env):
        # A web server answering the URL, not FoundryX itself - an HTML 404, no JSON.
        _patch_transport(monkeypatch, _canned_html_handler(404))

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts4"
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["message"] == "Not a FoundryX gateway"

    def test_ac_ts_5_connection_refused_means_unreachable(self, monkeypatch, route_env):
        # No TRANSPORT patch: real httpx networking against a closed local port, so
        # this is a genuine connection failure, not a canned response - within the
        # client's own connect timeout (no sleep needed for a closed port).
        import app.services.foundryx_autocount_client as client_mod

        monkeypatch.setattr(client_mod, "TRANSPORT", None, raising=False)

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url="http://127.0.0.1:9", api_key="fxa_ts5"
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["message"].startswith("Unreachable: ")

    def test_ac_ts_6_not_configured_is_a_200_test_result_not_an_error(self, monkeypatch, route_env):
        _patch_transport(monkeypatch, _no_call_allowed_handler())

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts6", active=False
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["message"] == "Base URL or key missing"

    def test_ac_ts_7_view_only_user_is_refused(self, monkeypatch, route_env):
        _patch_transport(monkeypatch, _no_call_allowed_handler())

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts7"
        )
        route_env.db.commit()
        # Holds view, deliberately NOT edit.
        route_env.as_user(_make_user(route_env.db, "integration.integrations.view"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 403

    def test_ac_ts_8_non_autocount_esb_type_is_400_test_not_supported(self, monkeypatch, route_env):
        _patch_transport(monkeypatch, _no_call_allowed_handler())

        row = _seed_non_esb_integration(route_env.db)
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        assert resp.status_code == 400
        assert "TEST_NOT_SUPPORTED" in resp.text

    def test_ac_ts_9_touches_neither_last_used_at_nor_last_error_nor_integration_log(
        self, monkeypatch, route_env
    ):
        from app.models.integration import Integration, IntegrationLog

        fake_client = TestClient(fake_foundryx.app)
        _patch_transport(monkeypatch, _forwarding_handler(fake_client))

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key="fxa_ts9"
        )
        row.last_used_at = None
        row.last_error = None
        route_env.db.commit()
        integration_id = row.id
        log_count_before = route_env.db.query(IntegrationLog).count()

        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))
        resp = route_env.post_test(integration_id)
        assert resp.status_code == 200

        refreshed = (
            route_env.db.query(Integration).filter(Integration.id == integration_id).one()
        )
        assert refreshed.last_used_at is None
        assert refreshed.last_error is None
        assert route_env.db.query(IntegrationLog).count() == log_count_before

    def test_ac_ts_9_the_key_never_leaks_into_the_response_or_caplog(
        self, monkeypatch, route_env, caplog
    ):
        api_key = "fxa_should_never_leak_ts9"
        fake_client = TestClient(fake_foundryx.app)
        _patch_transport(monkeypatch, _forwarding_handler(fake_client))
        caplog.set_level(logging.DEBUG)

        row = fake_foundryx.seed_foundryx_connection(
            route_env.db, base_url=FAKE_BASE_URL, api_key=api_key
        )
        route_env.db.commit()
        route_env.as_user(_make_user(route_env.db, "integration.integrations.edit"))

        resp = route_env.post_test(row.id)

        # The route must actually run (not 404) for this to prove anything - a
        # missing route trivially "leaks" nothing.
        assert resp.status_code == 200
        assert api_key not in resp.text
        for record in caplog.records:
            assert api_key not in record.getMessage()
