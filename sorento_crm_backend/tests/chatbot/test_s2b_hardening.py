"""S2b hardening: the review-pass findings on top of the shipped turn trace / retry
surface (`app/api/v1/system/chatbot.py`, `app/services/chatbot/dispatch.py`,
`app/services/chatbot_turn_sweep.py`, `app/services/chatbot/usage.py`, SEC2/SEC3/SEC4/SEC7
from the coordinator's review, AC-260).

Every scenario here targets code that is ALREADY IMPLEMENTED (this is a hardening pass,
not a red-then-green slice), so these tests are expected to pass against the current
`feat/chatbot-turn-engine-s2b` tree. Run with `CHATBOT_FIXTURES_DIR` pointed at the
captures worktree and at `/nonexistent` per the coordinator's instruction - nothing here
reads that variable directly (it only gates `tests/chatbot/test_replay.py`'s corpus
parametrisation), so both runs are expected to produce IDENTICAL results; this file's own
report notes that explicitly rather than assuming it.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip - registers every model before any query
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.access import RespondContact
from app.models.ai_assistant import AIAssistantUsageLog
from app.models.chatbot_turn import ChatbotTurn
from app.models.integration import Integration, IntegrationApiKey, IntegrationLog
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRoleAssignment,
    UserRolePermission,
)
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import trace as trace_mod
from app.services.chatbot.dispatch import ReinjectFailed, RetryUnavailable
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot_turn_sweep import SWEEP_BATCH, sweep_stalled_delegated_turns
from app.services.integration_key_service import IntegrationKeyService
from app.services.user_service import UserPermissionService
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures are used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

VIEW = "system.chat_history.view"
MANAGE = "system.chat_history.manage"
TURNS_BASE = "/api/v1/system/chatbot/turns"
_TURN_URL = "/api/v1/external/chat/turn"

_GRANTS: set[str] = set()
_ACTOR: dict = {"id": None, "name": "ZZT S2b Hardening Tester"}


# --------------------------------------------------------------------------- #
# Shared fixtures (mirrors tests/chatbot/test_turns_admin_api.py and
# tests/chatbot/test_chat_turn_endpoint.py; each test file in this suite owns its own
# fixtures rather than sharing across files - the established pattern here).
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db(session_factory):
    return session_factory()


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
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
def external_api_key(session_factory):
    """A real integration for `/external/chat/turn`, matching
    `test_chat_turn_endpoint.py::api_key` (duplicated per this suite's own convention)."""
    db = session_factory()
    user = User(
        email="chatbot-hardening@integrations.local",
        name="Integration: chatbot hardening test",
        status="ACTIVE",
        is_integration=True,
    )
    db.add(user)
    db.flush()
    role = UserRole(slug="integration_chatbot_hardening_test", name="Integration: chatbot hardening (test)")
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    permission = UserPermission(slug="integration.chat_turn.submit", name="Submit chatbot turns")
    db.add(permission)
    db.flush()
    db.add(UserRolePermission(role_id=role.id, permission_id=permission.id))
    integration = Integration(
        name="n8n-chatbot-hardening-test", type="n8n", act_as_user_id=user.id, is_active=True
    )
    db.add(integration)
    db.flush()
    issued = IntegrationKeyService(db).issue_key(integration)
    db.commit()
    return issued


@pytest.fixture()
def external_client(session_factory):
    def _override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _contact(label: str = "") -> str:
    return f"ZZT-contact-{label}-{uuid.uuid4().hex[:8]}"


def _seed_turn(
    db,
    *,
    contact_respond_id: str,
    status: str = "failed",
    stage: str | None = "understood",
    message_id: str | None = None,
    retry_requested_at=None,
    envelope: dict | None = None,
    attempt: int = 1,
) -> ChatbotTurn:
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_respond_id,
        message_id=message_id,
        ingress="webhook",
        envelope=envelope or {"message": {"messageId": message_id}, "contact": {"id": contact_respond_id}},
        status=status,
        stage=stage,
        attempt=attempt,
        trace=[
            {
                "stage": stage or "understood",
                "status": "failed",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ms": 10,
                "summary": "seeded failure",
                "why": "seeded",
                "facts": {},
                "error": "seeded error",
                "raw": None,
            }
        ],
        retry_requested_at=retry_requested_at,
        error="seeded error",
    )
    db.add(turn)
    db.commit()
    return turn


# =============================================================================
# (SEC1) After migration 474's grant step, only the admin role holds
# system.chat_history.manage - the grant is ADMIN ONLY (the migration's own docstring:
# ".view is held by two integration roles on the production data, and this slug
# re-injects a message at a real customer"), so holding .view is not enough on its
# own and an integration_% role never gets .manage regardless of what else it holds.
# =============================================================================

_MIGRATION_474_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "alembic"
    / "versions"
    / "474_chatbot_turn_retry.py"
)
_MANAGE_SLUG = "system.chat_history.manage"
_VIEW_SLUG = "system.chat_history.view"


def _migration_474_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_474", _MIGRATION_474_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _role_holding(db, role_slug: str, permission_slug: str | None) -> UserRole:
    role = UserRole(id=str(uuid.uuid4()), slug=role_slug, name=role_slug, description="", is_protected=False, is_default=False)
    db.add(role)
    db.flush()
    if permission_slug:
        perm = db.query(UserPermission).filter_by(slug=permission_slug).first()
        if perm is None:
            perm = UserPermission(id=str(uuid.uuid4()), slug=permission_slug, name=permission_slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
        db.flush()
    return role


def _role_manage_slugs(db, role_id: str) -> set[str]:
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT p.slug FROM user_role_permissions rp "
            "JOIN user_permissions p ON p.id = rp.permission_id "
            "WHERE rp.role_id = :role"
        ),
        {"role": role_id},
    ).all()
    return {row[0] for row in rows}


class TestSEC1ManageGrantScope:
    def test_only_admin_ends_up_holding_manage_integration_roles_do_not(self, db, monkeypatch):
        admin_role = _role_holding(db, "admin", None)  # no .view grant needed - the UNION names the slug directly
        integration_role_a = _role_holding(db, "integration_n8n", None)
        integration_role_b = _role_holding(db, "integration_sorento_mcp", None)
        db.commit()

        monkeypatch.setattr("alembic.op.get_bind", lambda: db.connection())
        _migration_474_module()._register_and_grant()

        assert _MANAGE_SLUG in _role_manage_slugs(db, admin_role.id)
        assert _MANAGE_SLUG not in _role_manage_slugs(db, integration_role_a.id)
        assert _MANAGE_SLUG not in _role_manage_slugs(db, integration_role_b.id)

    def test_holding_view_is_not_enough_on_its_own_admin_only(self, db, monkeypatch):
        """The grant is admin-only, full stop - a non-integration role holding `.view`
        (a customer-service role, say) must not pick up `.manage` just for that."""
        view_perm = UserPermission(id=str(uuid.uuid4()), slug=_VIEW_SLUG, name=_VIEW_SLUG)
        db.add(view_perm)
        db.flush()
        view_only_role = _role_holding(db, "customer_service", _VIEW_SLUG)
        admin_role = _role_holding(db, "admin", None)
        db.commit()

        monkeypatch.setattr("alembic.op.get_bind", lambda: db.connection())
        _migration_474_module()._register_and_grant()

        assert _MANAGE_SLUG not in _role_manage_slugs(db, view_only_role.id)
        assert _MANAGE_SLUG in _role_manage_slugs(db, admin_role.id)


# =============================================================================
# (2) Retry ordering under failure: RetryUnavailable and ReinjectFailed both roll
# back the claim and log the outcome.
# =============================================================================


class TestRetryFailureRollback:
    @pytest.mark.parametrize(
        "exc",
        [
            RetryUnavailable("no ingress configured"),
            ReinjectFailed(502, "n8n said no"),
        ],
        ids=["retry_unavailable", "reinject_failed"],
    )
    def test_a_failed_reinject_leaves_no_marker_and_no_dangling_note(
        self, client, db, monkeypatch, exc
    ):
        _GRANTS.add(MANAGE)
        contact = _contact("retry-rollback")
        turn = _seed_turn(db, contact_respond_id=contact)
        trace_before = list(turn.trace)

        monkeypatch.setattr(
            "app.api.v1.system.chatbot.reinject_envelope",
            lambda row: (_ for _ in ()).throw(exc),
        )

        resp = client.post(f"{TURNS_BASE}/{turn.id}/retry")
        assert resp.status_code in (409, 502), resp.text

        db.expire_all()
        reread = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn.id).one()
        # The claim must not stand: nothing was accepted by the ingress.
        assert reread.retry_requested_at is None
        # The "Retry requested" note is removed, not left dangling on a row that never
        # actually asked anything of n8n.
        assert reread.trace == trace_before
        assert reread.status == "failed"

        log = (
            db.query(IntegrationLog)
            .filter(IntegrationLog.business_id == str(turn.id))
            .order_by(IntegrationLog.created_at.desc())
            .first()
        )
        assert log is not None, "a failed retry must still write an integration_log row"
        assert log.status == "failed"
        assert log.status_code == resp.status_code


# =============================================================================
# (B2) Retry ordering pin: the marker is written and COMMITTED before the outbound
# POST goes out - the endpoint's own docstring calls the reverse order a race (n8n
# could re-deliver and the engine could look for the marker before this request's
# commit lands). Proven with a genuinely SEPARATE session opened INSIDE the
# `reinject_envelope` stub, not by re-reading the request's own session (which would
# trivially agree with an in-memory attribute regardless of whether anything landed).
# =============================================================================


class TestRetryOrderB2:
    def test_the_marker_is_committed_before_the_outbound_post(
        self, client, db, session_factory, monkeypatch
    ):
        _GRANTS.add(MANAGE)
        contact = _contact("retry-order-b2")
        turn = _seed_turn(db, contact_respond_id=contact)

        seen: dict[str, object] = {}

        def _stub(row):
            second_session = session_factory()
            try:
                reread = (
                    second_session.query(ChatbotTurn).filter(ChatbotTurn.id == row.id).one()
                )
                seen["retry_requested_at"] = reread.retry_requested_at
            finally:
                second_session.close()

        monkeypatch.setattr("app.api.v1.system.chatbot.reinject_envelope", _stub)

        resp = client.post(f"{TURNS_BASE}/{turn.id}/retry")
        assert resp.status_code == 200, resp.text

        assert seen.get("retry_requested_at") is not None, (
            "a second session opened INSIDE reinject_envelope must already see the "
            "committed retry_requested_at - the claim has to land before the POST"
        )


# =============================================================================
# (3) The stale window: a marker older than chatbot_retry_stale_minutes allows a
# second Retry; a fresh one 409s.
# =============================================================================


class TestRetryStaleWindow:
    def test_a_stale_marker_allows_retry_again_a_fresh_one_409s(
        self, client, db, monkeypatch
    ):
        _GRANTS.add(MANAGE)
        monkeypatch.setattr(settings, "chatbot_retry_stale_minutes", 5, raising=False)
        monkeypatch.setattr(
            "app.api.v1.system.chatbot.reinject_envelope", lambda row: None
        )

        stale_contact = _contact("retry-stale")
        stale_turn = _seed_turn(
            db,
            contact_respond_id=stale_contact,
            retry_requested_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        resp = client.post(f"{TURNS_BASE}/{stale_turn.id}/retry")
        assert resp.status_code == 200, resp.text

        fresh_contact = _contact("retry-fresh")
        fresh_turn = _seed_turn(
            db,
            contact_respond_id=fresh_contact,
            retry_requested_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        resp = client.post(f"{TURNS_BASE}/{fresh_turn.id}/retry")
        assert resp.status_code == 409, resp.text


# =============================================================================
# (4) SEC3: request body over 256 KB is 422 with a sentence and no turn row; an
# oversize response is stored as the cap note.
# =============================================================================


class TestSEC3RequestBodySize:
    def test_an_oversize_turn_body_is_422_and_writes_no_row(self, external_client, external_api_key, db):
        _GRANTS.add("integration.chat_turn.submit")
        oversize_envelope = {
            "message": {"messageId": "ZZT-msg-oversize"},
            "contact": {"id": CONTACT_ID},
            # `Envelope.model_config = extra="allow"`, so this rides along without
            # tripping any field validator - it exists purely to push the body over
            # the endpoint's 256 KB limit.
            "padding": "x" * (300 * 1024),
        }

        resp = external_client.post(
            _TURN_URL,
            json={"envelope": oversize_envelope},
            headers={"X-API-Key": external_api_key},
        )

        assert resp.status_code == 422, resp.text
        assert "byte limit" in resp.text.lower()
        assert "262144" in resp.text  # 256 * 1024, MAX_TURN_BODY_BYTES

        rows = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.contact_respond_id == CONTACT_ID)
            .all()
        )
        assert rows == [], "an oversize body must be rejected before any turn row is written"


class TestSEC3ResponseCap:
    def test_cap_document_replaces_an_oversize_document_with_a_note(self):
        huge = {"result_set": ["x" * 1000 for _ in range(1000)]}  # ~1 MB, well over the cap
        capped = trace_mod.cap_document(huge)

        assert isinstance(capped, dict)
        assert "note" in capped
        assert "byte" in capped["note"].lower()
        assert str(trace_mod.DOCUMENT_BYTE_CAP) in capped["note"]

    def test_cap_document_leaves_a_small_document_untouched(self):
        small = {"reply": {"text": "SRTWC8517: 12 pcs on hand."}}
        assert trace_mod.cap_document(small) == small


# =============================================================================
# (SEC6) Entity strings in trace summaries are clipped at 40 chars
# (trace.py::MAX_ENTITY_CHARS) - an entity's `raw` is CUSTOMER TEXT, and unclipped it
# turns a one-line "Understood as..." sentence into a paragraph on the trace screen.
# =============================================================================


class TestSEC6EntityClipping:
    def test_clip_leaves_a_short_string_untouched(self):
        assert trace_mod._clip("SRTWC8517") == "SRTWC8517"

    def test_clip_truncates_at_max_entity_chars_with_an_ellipsis(self):
        long_value = "x" * 100
        clipped = trace_mod._clip(long_value)

        assert len(clipped) == trace_mod.MAX_ENTITY_CHARS
        assert clipped.endswith("…")
        assert clipped[:-1] == long_value[: trace_mod.MAX_ENTITY_CHARS - 1]

    def test_clip_is_exactly_at_the_boundary_unclipped(self):
        exact = "x" * trace_mod.MAX_ENTITY_CHARS
        assert trace_mod._clip(exact) == exact
        over_by_one = "x" * (trace_mod.MAX_ENTITY_CHARS + 1)
        assert trace_mod._clip(over_by_one) != over_by_one
        assert len(trace_mod._clip(over_by_one)) == trace_mod.MAX_ENTITY_CHARS

    def test_understood_summary_clips_a_long_entity_raw(self):
        customer_text = "y" * 100
        qf = {
            "message_type": "business_query",
            "entities": [{"raw": customer_text, "canonical_code": None}],
        }

        summary = trace_mod.understood_summary(qf)

        assert customer_text not in summary
        assert trace_mod._clip(customer_text) in summary


# =============================================================================
# (5) SEC2: a live turn writes exactly one ai_assistant_usage_logs row with
# feature chatbot_parser; a dry run writes none; a failed parse still writes one.
# =============================================================================


class TestSEC2ParserUsageLogging:
    def _usage_rows(self, session_factory):
        db = session_factory()
        internal_id = (
            db.query(RespondContact.id)
            .filter(RespondContact.respond_io_id == CONTACT_ID)
            .scalar()
        )
        return (
            db.query(AIAssistantUsageLog)
            .filter(AIAssistantUsageLog.contact_id == internal_id)
            .filter(AIAssistantUsageLog.feature == "chatbot_parser")
            .all()
        )

    def test_a_live_turn_writes_exactly_one_row(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        # `ParsedOutput` (not a bare dict) is what carries `.usage` - `getattr(parser_raw,
        # "usage", {})` is the engine's whole contract for "did the provider bill for
        # this", and a plain dict answers "no", same as a bypassed parse.
        billed_usage = {"provider": "openai", "model": "gpt-test", "prompt_tokens": 12, "total_tokens": 20}
        stub_parser(output=parser_mod.ParsedOutput(_parser_output(), usage=billed_usage))
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        rows = self._usage_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].feature == "chatbot_parser"

    def test_a_dry_run_writes_none(self, session_factory, seeded, stub_parser, stub_access):
        stub_parser()
        stub_access()

        engine_mod.run_turn(
            _envelope(test_run_id="ZZT-clone-run"), session_factory=session_factory
        )

        assert self._usage_rows(session_factory) == []

    def test_a_failed_parse_with_billed_usage_still_writes_one_row(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        billed_usage = {"provider": "openai", "model": "gpt-test", "prompt_tokens": 40, "total_tokens": 55}
        stub_parser(error=parser_mod.ParserError("malformed JSON", usage=billed_usage))
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert result.status == "failed"

        rows = self._usage_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].was_answered is False
        assert rows[0].total_tokens == 55


# =============================================================================
# (6) SEC7: an over-long messageId / shadow_of is 422 naming the field.
# =============================================================================


class TestSEC7OverlongIdentifiers:
    def test_an_overlong_message_id_is_422_naming_the_field(self, external_client, external_api_key):
        _GRANTS.add("integration.chat_turn.submit")
        envelope = _envelope().model_dump(mode="json")
        envelope["message"]["message"]["messageId"] = "x" * 200

        resp = external_client.post(
            _TURN_URL,
            json={"envelope": envelope},
            headers={"X-API-Key": external_api_key},
        )

        assert resp.status_code == 422, resp.text
        assert "messageId" in resp.text

    def test_an_overlong_shadow_of_is_422_naming_the_field(self, external_client, external_api_key):
        _GRANTS.add("integration.chat_turn.submit")
        resp = external_client.post(
            _TURN_URL,
            json={
                "envelope": {
                    "message": {},
                    "contact": {"id": CONTACT_ID},
                    "shadow_of": "x" * 200,
                }
            },
            headers={"X-API-Key": external_api_key},
        )

        assert resp.status_code == 422, resp.text
        assert "shadow_of" in resp.text


# =============================================================================
# (7) AC-260 sweep edge cases: started_at NULL falls back to created_at; more
# than SWEEP_BATCH stale rows across two ticks.
# =============================================================================


class TestAC260SweepEdgeCases:
    NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    TTL = 10

    def _turn(self, db, *, age_minutes: int, started_at_null: bool = False) -> ChatbotTurn:
        created = self.NOW - timedelta(minutes=age_minutes)
        row = ChatbotTurn(
            contact_respond_id=f"ZZT-contact-{uuid.uuid4().hex[:8]}",
            message_id=f"ZZT-wamid-{uuid.uuid4().hex[:8]}",
            ingress="webhook",
            envelope={"message": {}, "contact": {"id": "ZZT"}},
            status="delegated",
            stage="routed",
            branch_kind="business_query",
            attempt=1,
            trace=[],
            started_at=None if started_at_null else created,
            created_at=created,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_a_null_started_at_falls_back_to_created_at(self, session_factory):
        db = session_factory()
        stale = self._turn(db, age_minutes=self.TTL + 5, started_at_null=True)
        fresh = self._turn(db, age_minutes=self.TTL - 5, started_at_null=True)

        settled = sweep_stalled_delegated_turns(db, now=self.NOW, ttl_minutes=self.TTL)
        assert settled == 1

        db.refresh(stale)
        db.refresh(fresh)
        assert stale.status == "failed"
        assert fresh.status == "delegated"

    def test_more_than_sweep_batch_stale_rows_take_two_ticks(self, session_factory):
        db = session_factory()
        total = SWEEP_BATCH + 7
        for _ in range(total):
            self._turn(db, age_minutes=self.TTL + 30)

        first_tick = sweep_stalled_delegated_turns(db, now=self.NOW, ttl_minutes=self.TTL)
        assert first_tick == SWEEP_BATCH

        remaining = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.status == "delegated")
            .count()
        )
        assert remaining == 7

        second_tick = sweep_stalled_delegated_turns(db, now=self.NOW, ttl_minutes=self.TTL)
        assert second_tick == 7

        still_delegated = (
            db.query(ChatbotTurn)
            .filter(ChatbotTurn.status == "delegated")
            .count()
        )
        assert still_delegated == 0


# =============================================================================
# (8) SEC4: TurnResponse.is_test equals the engine's dry-run verdict for
# is_test, test_run_id and mode != live.
# =============================================================================


class TestSEC4IsTestVerdict:
    @pytest.mark.parametrize(
        "overrides,expected",
        [
            ({"is_test": True}, True),
            ({"test_run_id": "ZZT-clone-run"}, True),
            ({"mode": "console"}, True),
            ({"mode": "live"}, False),
            ({}, False),
        ],
        ids=["is_test_flag", "test_run_id", "non_live_mode", "live_mode", "no_signal"],
    )
    def test_is_test_matches_the_engines_dry_run_verdict(
        self, session_factory, seeded, stub_parser, stub_access, overrides, expected
    ):
        stub_parser()
        stub_access()
        envelope = _envelope(**overrides)
        envelope.message["message"]["messageId"] = f"ZZT-msg-sec4-{uuid.uuid4().hex[:8]}"

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.is_test is expected
        # What actually ships on the wire: `TurnResponse(**result.as_dict())` in
        # `app/api/v1/external/chat.py`. Asserted here too so a change to `as_dict()`
        # that dropped or renamed the key would fail this test, not just a slower one.
        assert result.as_dict()["is_test"] is expected
