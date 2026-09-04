"""S6a tester slice: the delegate seam, the D14 dry-run boundary, and three gate
predicates the replay corpus cannot exercise (AC-601 to AC-603, D14, H38, H46).

Everything here is on Postgres (`tests/_pg_fixture.py` via `tests/chatbot/conftest.py`'s
`session_factory`), against a blank schema, seeding its own ZZT-prefixed rows. Nothing
touches the shared dev database.
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from app.config import settings
from app.services.chatbot import contracts
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business import resolve_gate
from app.services.chatbot.lanes.business.services import ResolveGateServices, production_services
from app.services.error_handler import AppException
from tests.chatbot.test_engine import (  # noqa: F401  - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    _turn_row,
    seeded,
    stub_access,
    stub_parser,
)

BUSINESS_ARMS = ("business_query", "check_promotion", "stock_denied")
OTHER_ARMS = tuple(k for k in contracts.BRANCH_KINDS if k not in BUSINESS_ARMS)


def _stub_bundle(calls: list[str], *, names: list[str] | None = None) -> ResolveGateServices:
    def _access_types(*, contact_id, space_id):
        calls.append("access_types")
        return [{"name": n} for n in (names or [])]

    def _resolve_entity(body):
        calls.append("resolve_entity")
        return {"tokens": [], "resolutions": [], "unresolved_tokens": []}

    def _probe(**kwargs):
        calls.append("probe")
        return None

    return ResolveGateServices(access_types=_access_types, resolve_entity=_resolve_entity, probe=_probe)


# --------------------------------------------------------------------------- #
# 1. AC-601 delegate seam: flag on/off, three arms in, ten arms untouched.
# --------------------------------------------------------------------------- #


class TestS6aDelegateSeamFlagGating:
    @pytest.mark.parametrize("branch_kind", BUSINESS_ARMS)
    def test_flag_on_the_three_business_arms_delegate_with_an_exit_kind_payload(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch, branch_kind
    ) -> None:
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        calls: list[str] = []
        bundle = _stub_bundle(calls, names=["Sorento Dealer"])
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(engine_mod, "decide", lambda ctx, *, stock_denial_enabled: (branch_kind, {}))
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == branch_kind
        assert result.delegate == "business_query"  # the one lane all three arms resume on
        assert result.delegate_payload is not None
        assert result.delegate_payload["_exit_kind"] in contracts.EXIT_KINDS
        assert calls, f"{branch_kind}: the lane's seams never ran"

    @pytest.mark.parametrize("branch_kind", OTHER_ARMS)
    def test_flag_on_the_ten_other_arms_never_touch_the_lane(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch, branch_kind
    ) -> None:
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        calls: list[str] = []
        bundle = _stub_bundle(calls)
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        monkeypatch.setattr(engine_mod, "decide", lambda ctx, *, stock_denial_enabled: (branch_kind, {}))
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == branch_kind
        assert result.delegate_payload is None
        assert calls == [], f"{branch_kind} reached the business lane's seams"

    def test_flag_off_the_lane_never_runs_for_a_business_arm(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """Default (off) behaviour: unchanged from before S6a shipped."""
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", False)
        calls: list[str] = []
        bundle = _stub_bundle(calls)
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        stub_parser()  # default qf routes to business_query
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query"
        assert result.delegate_payload is None
        assert calls == [], "the lane ran even though the flag is off"

    @pytest.mark.parametrize("branch_kind", ("check_promotion", "stock_denied"))
    def test_flag_off_delegate_is_the_bare_branch_kind_not_the_lane_name(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch, branch_kind
    ) -> None:
        """With the flag off, `delegate` is n8n's own tag - never overwritten to
        `business_query`, which is only what the LANE resumes on once it runs."""
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", False)
        monkeypatch.setattr(engine_mod, "decide", lambda ctx, *, stock_denial_enabled: (branch_kind, {}))
        stub_parser()
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.delegate == branch_kind
        assert result.delegate_payload is None


# --------------------------------------------------------------------------- #
# 2. Shadow failure path: a resolver blow-up is recorded, never a 500.
# --------------------------------------------------------------------------- #


class TestShadowFailurePath:
    def test_a_resolver_failure_still_completes_the_turn_delegated(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)

        def _boom(body):
            raise RuntimeError("resolve-entity is down")

        bundle = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=_boom, probe=lambda **_: None
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        stub_parser()  # default qf -> business_query
        stub_access()

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "delegated"
        assert result.branch_kind == "business_query"
        assert result.delegate == "business_query"
        assert result.delegate_payload is None

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "delegated"
        assert row.error is None, "the SHADOW lane's failure must not fail the turn itself"
        looked_up = [r for r in row.trace if r["stage"] == "looked_up"]
        assert len(looked_up) == 1, row.trace
        assert looked_up[0]["status"] == "failed"
        assert "resolve-entity is down" in (looked_up[0].get("error") or "")


# --------------------------------------------------------------------------- #
# 3. D14 zero writes, with the lane ON, through the REAL resolve_entity seam.
# --------------------------------------------------------------------------- #


class _StubSpecResult:
    content = "{}"
    prompt_tokens = 1
    completion_tokens = 1
    total_tokens = 2


class _StubSpecProvider:
    def chat(self, messages, **kwargs):
        return _StubSpecResult()


class TestD14ZeroWritesWithTheLaneOnRealResolver:
    def test_a_dry_run_turn_through_the_real_resolver_writes_no_usage_log(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """D14 says a dry-run turn writes ZERO rows outside `chatbot.turns`. The business
        lane's `resolve_entity` seam is the REAL `POST /system/references/resolve` route
        function (`app/services/chatbot/lanes/business/services.py::_resolve_entity`),
        which has no concept of `envelope.dry_run` at all - it is a general system route,
        not a chatbot-aware one. `resolve_gate.resolve_entity_body` unconditionally sets
        `spec_fallback: True` and `understand_phrase: True`
        (app/services/chatbot/lanes/business/resolve_gate.py:206-208), so a token that
        misses every normal probe (guaranteed on this blank schema) falls into the spec
        search path, which - when a model is configured - unconditionally writes an
        `ai_assistant_usage_logs` row and commits
        (app/services/product_spec_understanding.py:597-614, inside `understand_phrase`),
        with no dry-run guard anywhere in that call chain.
        """
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        # `understand_phrase` writes `user_id=current_user.get("id")` off this setting; a
        # non-existent id makes the INSERT fail on a users.id FK instead of on dry-run
        # gating - which would make this test pass for the WRONG reason (measured: with
        # the real unseeded id the write 500s on FK, not on any dry-run check). NULL is a
        # legitimate value for this nullable column and isolates the one thing under test.
        monkeypatch.setattr(settings, "external_api_key_act_as_user_id", None)

        import app.services.product_spec_understanding as psu

        stub_provider = _StubSpecProvider()
        monkeypatch.setattr(
            psu,
            "_resolve_provider",
            lambda db, agent_name=psu.AGENT_NAME: (stub_provider, "stub-provider", "stub-model"),
        )

        qf = _parser_output(
            entities=[
                {
                    "raw": "ZZTNOSUCHPRODUCT999",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                }
            ]
        )
        stub_parser(qf)
        stub_access()

        envelope = _envelope(test_run_id="ZZT-run-s6a-1")
        envelope.message["message"]["message"]["text"] = "price for ZZTNOSUCHPRODUCT999"
        assert envelope.dry_run is True

        db = session_factory()
        usage_before = db.execute(text("SELECT COUNT(*) FROM ai_assistant_usage_logs")).scalar()
        session_vars_before = db.execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        after_db = session_factory()
        usage_after = after_db.execute(text("SELECT COUNT(*) FROM ai_assistant_usage_logs")).scalar()
        session_vars_after = after_db.execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        ).scalar()

        assert result.branch_kind == "business_query"
        assert session_vars_after == session_vars_before, "D14: session_vars must be untouched"
        assert usage_after == usage_before, (
            "DEFECT (D14): a dry-run turn wrote an ai_assistant_usage_logs row. The "
            "business lane's resolve_entity seam "
            "(app/services/chatbot/lanes/business/services.py::_resolve_entity) calls "
            "the real resolve_reference_post regardless of envelope.dry_run, and that "
            "route's spec-search fallback "
            "(app/services/product_spec_understanding.py:597-614, understand_phrase) "
            "writes and commits AIAssistantUsageLog unconditionally whenever a model is "
            "configured - it has no dry-run parameter anywhere in the call chain."
        )


# --------------------------------------------------------------------------- #
# 4. Capacity rule: no DB session open during the resolver seam call.
# --------------------------------------------------------------------------- #


class TestCapacityRuleDuringResolverSeam:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "engine.py's own docstring at the S6a call site (app/services/chatbot/"
            "engine.py, the 'looked_up' stage comment beginning 'It runs INSIDE this "
            "session on purpose') documents that the resolver runs inside the same "
            "session opened for access/routed, holding it across the resolver's "
            "optional spec-search LLM call - the one place this turn breaks the plan's "
            "'never hold a DB session across provider I/O' rule. S6b owns the split "
            "into its own stage; flip this test green once that lands."
        ),
    )
    def test_no_db_session_is_open_during_the_resolver_seam_call(
        self, counting_session_factory, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "chatbot_business_lane_enabled", True)
        observed: list[int] = []

        def _resolve_entity(body):
            observed.append(counting_session_factory.state["open"])
            return {"tokens": [], "resolutions": [], "unresolved_tokens": []}

        bundle = ResolveGateServices(
            access_types=lambda **_: [{"name": "Sorento Dealer"}],
            resolve_entity=_resolve_entity,
            probe=lambda **_: None,
        )
        monkeypatch.setattr(
            engine_mod.business_services,
            "production_services",
            lambda db, *, space_id=None: bundle,
        )
        stub_parser()
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=counting_session_factory)

        assert observed == [0], (
            "a DB session was held open during the resolver seam call - the S6a lane "
            "must close it before the resolver's optional LLM call and reopen after, "
            "the same discipline the parser call already has"
        )


# --------------------------------------------------------------------------- #
# 5. check_promotion end to end, real ContactAccessTypeService on Postgres.
# --------------------------------------------------------------------------- #


class TestCheckPromotionRealAccessTypeService:
    SPACE_ID = "364817-zzt"

    def _seed_workspace_and_contact(self, db) -> None:
        from app.models.respond_workspace import RespondWorkspace

        db.execute(
            text(
                "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext) "
                "VALUES (gen_random_uuid(), :space_id, 'ZZT workspace', 'zzt-cipher') "
                "ON CONFLICT DO NOTHING"
            ),
            {"space_id": self.SPACE_ID},
        )
        db.execute(
            text(
                "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
                "SELECT gen_random_uuid()::text, :cid, :phone, '{\"variables\": {}}'::jsonb, w.id "
                "FROM respond_workspaces w WHERE w.space_id = :space_id "
                "ON CONFLICT DO NOTHING"
            ),
            {"cid": CONTACT_ID, "phone": "+60000000010", "space_id": self.SPACE_ID},
        )
        db.commit()

    def _assign_access_type(self, db, *, code: str, name: str) -> None:
        db.execute(
            text(
                "INSERT INTO contact_access_types (code, name, is_active) "
                "VALUES (:code, :name, true) ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "name": name},
        )
        db.execute(
            text(
                "INSERT INTO respond_contact_access_types (contact_id, access_type_code) "
                "SELECT c.id, :code FROM respond_contacts c WHERE c.respond_io_id = :cid"
            ),
            {"code": code, "cid": CONTACT_ID},
        )
        db.commit()

    def _services(self, db) -> ResolveGateServices:
        from app.services.chatbot.lanes.business.services import production_services

        real = production_services(db, space_id=self.SPACE_ID)

        def _resolve_entity(body):
            raise AssertionError("resolve-entity must not run when If4 takes its FALSE leg")

        return ResolveGateServices(
            access_types=real.access_types, resolve_entity=_resolve_entity, probe=lambda **_: None
        )

    def _ctx(self) -> dict[str, Any]:
        return {
            "contact": {"id": CONTACT_ID},
            "parse": {"output": {"domain_hint": "promotion", "entities": []}},
            "session": {},
        }

    def test_no_tier_asks(self, session_factory) -> None:
        db = session_factory()
        self._seed_workspace_and_contact(db)
        # No access type assigned at all: zero entitlement names.

        out = resolve_gate.run(
            self._ctx(), "access_check", {}, services=self._services(db), space_id=self.SPACE_ID
        )
        assert out["_exit_kind"] == "access_ask"
        assert out["aggregate"] == {"name": []}

    def test_one_tier_continues(self, session_factory) -> None:
        db = session_factory()
        self._seed_workspace_and_contact(db)
        self._assign_access_type(db, code="zzt_sorento_dealer", name="Sorento Dealer")

        def _resolve_entity(body):
            return {"tokens": [], "resolutions": [], "unresolved_tokens": []}

        real = production_services(db, space_id=self.SPACE_ID)
        services = ResolveGateServices(
            access_types=real.access_types, resolve_entity=_resolve_entity, probe=lambda **_: None
        )
        out = resolve_gate.run(
            self._ctx(), "access_check", {}, services=services, space_id=self.SPACE_ID
        )
        assert out["_exit_kind"] != "access_ask"
        assert out["aggregate"] == {"name": ["Sorento Dealer"]}
        assert out["resolved"] is not None


# --------------------------------------------------------------------------- #
# 6. `_locale_compare`, `entity_pins` AND-mode omission, and the 400 pin mismatch.
# --------------------------------------------------------------------------- #


class TestLocaleCompareMixedCase:
    def test_all_lowercase_sorts_before_capitalised_at_equal_primary_strength(self) -> None:
        from app.services.chatbot.lanes.business.gate import _locale_compare

        assert _locale_compare("acme", "Acme") == -1
        assert _locale_compare("Acme", "acme") == 1
        assert _locale_compare("Acme", "Acme") == 0

    def test_a_mixed_case_company_pair(self) -> None:
        from app.services.chatbot.lanes.business.gate import _locale_compare

        assert _locale_compare("mastile klang sdn bhd", "Mastile Klang Sdn Bhd") == -1
        assert _locale_compare("Mastile Klang Sdn Bhd", "mastile klang sdn bhd") == 1


class TestEntityPinsBody:
    def _ctx(self, *, match_mode: str) -> dict[str, Any]:
        return {
            "contact": {"id": "c1"},
            "text": {"message": {"message": {"text": "ZZT-1"}}},
            "parse": {
                "output": {
                    "match_mode": match_mode,
                    "entities": [
                        {
                            "hint": "product",
                            "raw": "ZZT-1",
                            "uuid": "11111111-1111-1111-1111-111111111111",
                            "canonical_code": "ZZT-1",
                        }
                    ],
                }
            },
        }

    def test_and_mode_omits_entity_pins_even_with_a_pinned_uuid(self) -> None:
        body = resolve_gate.resolve_entity_body(self._ctx(match_mode="and"))
        assert "entity_pins" not in body
        assert body["match_mode"] == "and"

    def test_or_mode_with_a_pinned_uuid_carries_entity_pins(self) -> None:
        body = resolve_gate.resolve_entity_body(self._ctx(match_mode="or"))
        assert body["entity_pins"] == {"ZZT1": "11111111-1111-1111-1111-111111111111"}


class TestEntityPinMismatchSurfaces:
    """H38, through the IN-PROCESS call the S6a seam actually makes - no HTTP round trip."""

    def test_a_pin_the_resolver_cannot_match_raises_the_400_through_the_seam(
        self, session_factory
    ) -> None:
        db = session_factory()
        services = production_services(db)
        body = {
            "query": "ZZT-NOMATCH-1",
            "tokens": ["ZZT-NOMATCH-1"],
            "match_mode": "or",
            "allowed_entity_types": ["product"],
            "entity_pins": {"ZZT-NOMATCH-1": "22222222-2222-2222-2222-222222222222"},
        }
        with pytest.raises(AppException) as excinfo:
            services.resolve_entity(body)
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail["code"] == "ENTITY_PIN_MISMATCH"


# --------------------------------------------------------------------------- #
# 7. `is_timeline` contains-sentinel (H46) - the three shapes named in the brief.
# --------------------------------------------------------------------------- #


class TestIsTimelineContainsSentinel:
    def test_the_three_named_shapes(self) -> None:
        assert contracts.is_timeline(["__all__", "eta_delay_date"]) is True
        assert contracts.is_timeline(["eta_delay_date"]) is False
        assert contracts.is_timeline([]) is False
