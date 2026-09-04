"""O2: the three harness keys a DRY-RUN envelope may carry (AC-112).

Agreed with the n8n side so the fail-closed clone and the chat console can drive a turn
without an LLM and without the contact's real memory. Named after the n8n guards they
replace: **G6** is the reformulator bypass, **G8** is the session injection.

The rule has two halves and both are the contract:

* on a DRY RUN (`is_test`, a `test_run_id`, or `mode != live`) the keys are HONOURED;
* on a LIVE envelope they are IGNORED, and the fact that one was present is recorded as
  `harness_keys_ignored` on the `received` trace record - silence there would let a
  harness envelope reach a real customer and answer them from a mock.

Postgres only, blank schema, via `tests/chatbot/conftest.py`. Nothing here reaches an LLM:
the point of G6 is that there is no provider call to reach.
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    _turn_row,
    seeded,
    stub_access,
    stub_parser,
)


def _record(trace: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    rows = [r for r in trace if r["stage"] == stage]
    assert len(rows) == 1, f"expected exactly one {stage!r} record, got {len(rows)}: {trace}"
    return rows[0]


def _mock_output(**overrides: Any) -> dict[str, Any]:
    """A parser emission the harness supplies INSTEAD of the model's."""
    return _parser_output(user_goal="supplied by the harness", **overrides)


@pytest.fixture()
def exploding_parser(monkeypatch):
    """`parser.parse` must NEVER be called on a bypassed turn - so make it fatal.

    A stub that merely records the call would let a bypass that silently fell through to
    the model still pass, because the stub's output is shaped like a real one.
    """

    def fake_resolve_config(db, *, current_date):
        return parser_mod.ParserConfig(
            system_prompt="stub",
            prompt_version=1,
            provider="openai",
            model="gpt-test",
            api_key="sk-test",
        )

    def never(config, user_block):  # pragma: no cover - the assertion IS that it never runs
        raise AssertionError(
            "the parser was called on a turn the harness bypassed: G6 did not take effect"
        )

    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", never)


def _session_vars(session_factory) -> Any:
    return (
        session_factory()
        .execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": CONTACT_ID},
        )
        .scalar()
    )


class TestHarnessInjectionsG6:
    """`mock_reformulator_output` replaces the parser LLM call, on a dry run only."""

    def test_a_dry_run_bypasses_the_parser_and_post_processes_the_mock(
        self, session_factory, seeded, exploding_parser, stub_access
    ) -> None:
        stub_access()
        envelope = _envelope(
            test_run_id="ZZT-o2-g6",
            mock_reformulator_output=_mock_output(domain_hint="inventory"),
        )
        assert envelope.dry_run is True

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        # The mock went through the SAME post-processing a real parse takes, so the turn
        # routes off derived state, not off whatever the harness happened to type.
        assert result.ctx["parse"]["output"]["domain_hint"] == "inventory"
        assert result.ctx["parse"]["output"]["user_goal"] == "supplied by the harness"
        assert result.ctx["parse"]["_parser_raw"]["domain_hint"] == "inventory"
        assert result.branch_kind is not None

    def test_the_understood_record_says_the_parser_was_bypassed(
        self, session_factory, seeded, exploding_parser, stub_access
    ) -> None:
        stub_access()
        result = engine_mod.run_turn(
            _envelope(is_test=True, mock_reformulator_output=_mock_output()),
            session_factory=session_factory,
        )
        record = _record(_turn_row(session_factory, result.turn_id).trace, "understood")
        assert record["summary"] == "Parser bypassed by harness."
        assert record["facts"]["parser_bypassed"] is True
        # Still a legible sentence, like every other record (AC-007).
        assert " " in record["summary"] and " " in record["why"]

    def test_a_malformed_mock_is_a_failed_understood_stage_not_a_crash(
        self, session_factory, seeded, exploding_parser, stub_access
    ) -> None:
        """The harness handed us something that is not a parser emission.

        It takes the SAME path a malformed model answer takes (R5 / H44): a failed turn at
        `understood` with today's error reply, never a soft default and never a 500.
        """
        stub_access()
        result = engine_mod.run_turn(
            _envelope(is_test=True, mock_reformulator_output="not an object"),
            session_factory=session_factory,
        )
        assert result.status == "failed"
        assert result.stage == "understood"
        assert _turn_row(session_factory, result.turn_id).status == "failed"

    def test_a_live_envelope_ignores_the_mock_and_says_so(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """The model is asked, the mock is not used, and the stray key is VISIBLE."""
        stub_parser(_parser_output(domain_hint="order"))
        stub_access()
        envelope = _envelope(mock_reformulator_output=_mock_output(domain_hint="inventory"))
        assert envelope.dry_run is False

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.ctx["parse"]["output"]["domain_hint"] == "order", (
            "a live turn must answer from the model, never from an envelope key"
        )
        received = _record(_turn_row(session_factory, result.turn_id).trace, "received")
        assert received["facts"]["harness_keys_ignored"] == ["mock_reformulator_output"]
        understood = _record(_turn_row(session_factory, result.turn_id).trace, "understood")
        assert understood["facts"].get("parser_bypassed") is not True

    def test_a_live_turn_without_harness_keys_records_an_empty_list(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """Absent must not be indistinguishable from ignored: the key is always present."""
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        received = _record(_turn_row(session_factory, result.turn_id).trace, "received")
        assert received["facts"]["harness_keys_ignored"] == []


class TestHarnessInjectionsG8:
    """`previous_conversation_state` / `referenced_result_set` replace the stored memory."""

    CARRIED = {
        "domain_hint": "incoming",
        "selection_context": "disambiguation",
        "last_result_set": [{"idx": 1, "code": "ZZT-1"}],
    }
    REFERENCED = [{"idx": 1, "code": "ZZT-QUOTED"}]

    def test_a_dry_run_uses_the_injected_state_instead_of_the_stored_one(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        seen: dict[str, Any] = {}

        def _capture(user_block):
            seen["user_block"] = user_block

        stub_parser(on_call=_capture)
        stub_access()

        result = engine_mod.run_turn(
            _envelope(
                is_test=True,
                previous_conversation_state=self.CARRIED,
                referenced_result_set=self.REFERENCED,
            ),
            session_factory=session_factory,
        )

        session = result.ctx["session"]["session_vars"]
        assert session["variables"] == self.CARRIED
        assert session["referenced_result_set"] == self.REFERENCED
        assert seen["user_block"], "the parser still runs on an injected-state turn"

    def test_the_injected_state_is_never_written_back(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """D14's zero-writes rule, at the one place O2 could have broken it."""
        stub_parser()
        stub_access()
        before = _session_vars(session_factory)

        engine_mod.run_turn(
            _envelope(
                test_run_id="ZZT-o2-g8",
                previous_conversation_state=self.CARRIED,
                referenced_result_set=self.REFERENCED,
            ),
            session_factory=session_factory,
        )

        assert _session_vars(session_factory) == before

    def test_zero_rows_outside_chatbot_turns_on_an_injected_dry_run(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        stub_parser()
        stub_access()
        db = session_factory()
        turns_before = db.query(ChatbotTurn).count()
        contacts_before = db.execute(text("SELECT COUNT(*) FROM respond_contacts")).scalar()

        engine_mod.run_turn(
            _envelope(is_test=True, previous_conversation_state=self.CARRIED),
            session_factory=session_factory,
        )

        after = session_factory()
        assert after.query(ChatbotTurn).count() == turns_before + 1, "the turn row IS written"
        assert (
            after.execute(text("SELECT COUNT(*) FROM respond_contacts")).scalar()
            == contacts_before
        )

    def test_a_live_envelope_ignores_the_injection_and_says_so(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        stub_parser()
        stub_access()
        envelope = _envelope(
            previous_conversation_state=self.CARRIED, referenced_result_set=self.REFERENCED
        )
        assert envelope.dry_run is False

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        session = result.ctx["session"]["session_vars"]
        assert session["variables"] == {}, (
            "a live turn reads the CONTACT's memory; an envelope key must not replace it"
        )
        received = _record(_turn_row(session_factory, result.turn_id).trace, "received")
        assert received["facts"]["harness_keys_ignored"] == [
            "previous_conversation_state",
            "referenced_result_set",
        ]

    def test_all_three_ignored_keys_are_listed_in_a_stable_order(
        self, session_factory, seeded, stub_parser, stub_access
    ) -> None:
        """One list, in the order the contract declares them, so a diff of two traces is
        readable rather than order-dependent."""
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(
            _envelope(
                mock_reformulator_output=_mock_output(),
                previous_conversation_state=self.CARRIED,
                referenced_result_set=self.REFERENCED,
            ),
            session_factory=session_factory,
        )
        received = _record(_turn_row(session_factory, result.turn_id).trace, "received")
        assert received["facts"]["harness_keys_ignored"] == [
            "mock_reformulator_output",
            "previous_conversation_state",
            "referenced_result_set",
        ]
