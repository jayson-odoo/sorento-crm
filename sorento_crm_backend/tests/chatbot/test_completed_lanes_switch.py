"""`system_settings.chatbot_completed_lanes`: the CRM finishes a lane only when told to.

Two conditions decide whether a turn ends in the CRM or goes to n8n:

* `contracts.CRM_COMPLETED_BRANCH_KINDS` - what this BUILD can complete. It grows one
  slice at a time and is a fact about the code.
* `system_settings.chatbot_completed_lanes` - what the OWNER has switched on.

Both are required. That is what lets a lane deploy on its own: the code lands inert, the
CRM's answer is compared against n8n's for as long as the owner wants, then one string is
added to the settings row, and only after that is the n8n Switch output deleted. Without
the second condition the CRM starts answering the instant it deploys and the n8n edit has
to land in the same window or the lane runs twice.

Nothing here reaches an LLM, n8n or respond.io.
"""
from __future__ import annotations

import logging

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import BRANCH_KINDS, CRM_COMPLETED_BRANCH_KINDS
from app.services.chatbot.delegate import delegate_for, enabled_lanes_from
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    _envelope,
    _parser_output,
    _turn_row,
    seeded,
    stub_access,
    stub_parser,
)


class TestTheTwoConditions:
    """`delegate_for` on its own, both axes."""

    def test_a_lane_the_code_can_complete_still_delegates_until_it_is_enabled(self):
        assert "low_signal" in CRM_COMPLETED_BRANCH_KINDS
        assert delegate_for("low_signal") == "low_signal"
        assert delegate_for("low_signal", frozenset()) == "low_signal"

    def test_enabling_it_is_what_completes_it(self):
        assert delegate_for("low_signal", frozenset({"low_signal"})) is None

    def test_enabling_a_lane_the_code_cannot_complete_does_nothing(self):
        """The settings row cannot switch on a lane that has not been built.

        This is the direction that matters: an owner adding `business_query` before S6
        ships must NOT get a turn answered by a lane that does not exist.
        """
        not_built = sorted(set(BRANCH_KINDS) - CRM_COMPLETED_BRANCH_KINDS)
        assert not_built, "every lane is built - this test has outlived the migration"
        for kind in not_built:
            assert delegate_for(kind, frozenset({kind})) == kind, kind

    def test_unreadable_settings_fail_towards_n8n(self):
        """`None` means "nothing enabled", never "everything"."""
        assert delegate_for("low_signal", None) == "low_signal"


class TestParsingTheSettingsValue:
    """Operator data typed into a form: every bad shape degrades, none raises."""

    def test_the_happy_shape(self):
        assert enabled_lanes_from(["low_signal"]) == frozenset({"low_signal"})

    def test_absent_is_empty(self):
        assert enabled_lanes_from(None) == frozenset()
        assert enabled_lanes_from([]) == frozenset()

    def test_an_unknown_kind_is_ignored_with_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert enabled_lanes_from(["low_signal", "lowsignal"]) == frozenset({"low_signal"})
        assert "lowsignal" in caplog.text
        assert "not a branch kind" in caplog.text

    def test_a_non_string_entry_is_ignored_with_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert enabled_lanes_from(["low_signal", 7, None]) == frozenset({"low_signal"})
        assert "not a string" in caplog.text

    def test_a_non_list_value_disables_everything_with_a_warning(self, caplog):
        """A string is the likely typo (`"low_signal"` instead of `["low_signal"]`), and
        iterating it would enable nothing while looking like it enabled eleven letters."""
        with caplog.at_level(logging.WARNING):
            assert enabled_lanes_from("low_signal") == frozenset()
        assert "not a list" in caplog.text


class TestEndToEndThroughRunTurn:
    """The switch decides, on the real Postgres fixture the rest of this suite uses."""

    @staticmethod
    def _casual(stub_parser, stub_access):
        stub_parser(_parser_output(message_type="casual", domain_hint=None, intent_hint=None))
        stub_access()

    @staticmethod
    def _enable(row, lanes):
        """Set the switch and COMMIT it.

        The engine opens its own sessions off the factory. They share one connection
        inside the fixture's outer transaction, so an uncommitted attribute on the
        fixture's own session is invisible to them - the turn would read `[]` and the test
        would pass for the wrong reason.
        """
        from sqlalchemy.orm import object_session

        row.chatbot_completed_lanes = lanes
        object_session(row).commit()

    def test_default_empty_delegates_low_signal_and_runs_no_clarifier(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        """Default `[]`: the turn goes to n8n exactly as it did before S4, and the
        clarifier is never called - a lane that is switched off must not spend a model
        call on an answer nobody reads."""
        assert (system_settings_row.chatbot_completed_lanes or []) == []
        self._casual(stub_parser, stub_access)

        from app.services.chatbot.lanes import casual

        called: list[str] = []
        monkeypatch.setattr(
            casual, "resolve_clarifier_config", lambda db: called.append("config") or object()
        )
        monkeypatch.setattr(
            casual, "call_clarifier", lambda config, prompt: called.append("call") or "{}"
        )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "low_signal"
        assert result.delegate == "low_signal"
        assert result.reply is None
        assert result.actions == []
        assert called == [], "the clarifier ran for a lane that is switched off"

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "delegated"
        assert row.stage == "routed"

    def test_enabling_the_lane_completes_it_in_the_crm(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        self._enable(system_settings_row, ["low_signal"])
        self._casual(stub_parser, stub_access)

        from app.services.chatbot.lanes import casual

        monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
        monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db: object())
        monkeypatch.setattr(
            casual, "call_clarifier", lambda config, prompt: '{"response": "Hi there!"}'
        )

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "low_signal"
        assert result.delegate is None
        assert result.reply["text"] == "Hi there!"
        assert [a["kind"] for a in result.actions] == ["send_message"]

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "done", row.error
        assert row.stage == "casual_llm"

    def test_an_unknown_kind_in_the_row_does_not_enable_anything(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, caplog
    ):
        """A typo in the settings form leaves the turn delegating, and says so in the log
        rather than failing the turn."""
        self._enable(system_settings_row, ["low-signal", "lowsignal"])
        self._casual(stub_parser, stub_access)

        with caplog.at_level(logging.WARNING):
            result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.delegate == "low_signal"
        assert "not a branch kind" in caplog.text

    def test_the_settings_row_is_read_on_the_routing_session_not_a_new_one(
        self,
        counting_session_factory,
        seeded,
        system_settings_row,
        stub_parser,
        stub_access,
        monkeypatch,
    ):
        """No session is opened just to read the switch.

        `_enabled_lanes` is called with the session the routing stage already holds, so
        the count of open sessions at that moment is whatever routing itself opened - one -
        and never one more.
        """
        self._enable(system_settings_row, ["low_signal"])
        self._casual(stub_parser, stub_access)

        observed: list[int] = []
        original = engine_mod._enabled_lanes

        def watched(db):
            observed.append(counting_session_factory.state["open"])
            return original(db)

        monkeypatch.setattr(engine_mod, "_enabled_lanes", watched)

        from app.services.chatbot.lanes import casual

        monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
        monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db: object())
        monkeypatch.setattr(casual, "call_clarifier", lambda config, prompt: '{"response": "hi"}')

        engine_mod.run_turn(_envelope(), session_factory=counting_session_factory)

        assert observed == [1], (
            "the switch was read outside the routing session (or read more than once): "
            f"open-session counts at each read were {observed}"
        )


class TestTheSettingsSurface:
    """A new column reaches the frontend only if it is on BOTH manual builders."""

    def test_it_is_on_the_update_schema(self):
        from app.api.v1.user_management.settings import SystemSettingUpdate

        assert "chatbot_completed_lanes" in SystemSettingUpdate.model_fields

    def test_it_is_on_the_get_dict_builder(self):
        """Greps the route source: the GET body is a hand-built dict, and a column missing
        from it never reaches the FE however correct the column is."""
        import inspect

        from app.api.v1.user_management import settings as settings_mod

        source = inspect.getsource(settings_mod)
        assert '"chatbot_completed_lanes":' in source

    def test_it_is_not_on_app_config(self):
        """`/app-config` is the unauthenticated slice. Which lanes the CRM completes is an
        internal deployment detail and has no business being on it."""
        from app.api.v1.user_management.settings import AppConfigResponse

        assert "chatbot_completed_lanes" not in AppConfigResponse.model_fields
