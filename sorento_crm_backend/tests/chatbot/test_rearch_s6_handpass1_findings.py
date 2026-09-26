"""Owner hand-pass-1 findings 2a / 2b / D14 (16 Sep 2026, AC-1593).

`documentation/plans/chatbot/evidence/turn-rearch/hand-pass-1-16sep.md` finding 2:
`incoming srtwc286` -> roster -> `1` came back `access_denied` twice over. Two distinct
causes, tested separately here:

- 2b: `engine.run_turn` checked access on the parser's RAW `routing.suggested_agent`;
  the `DEFAULT_SUGGESTED_AGENT` fallback only ran later, in `lane_parse_output`, for the
  lanes - so a verdict that named no agent (most casual and many business turns) asked
  the access service about agent `None`, which fails closed as `deny_unknown_agent`.
  The fix (`turn_runtime.with_routing_agent_default`) must apply the default ONCE,
  before the access read, so a contact granted the default agent is never denied for a
  turn that simply named none; `access_denied` fires only when the contact genuinely
  lacks the grant.
- 2a / D14: a dry-run turn that opens a pending (clarify/roster/offer) must hand back
  `TurnResult.session_patch` (not None) carrying the open question, so the console UI
  (and any other caller) can chain the next turn without losing the pending - and it
  must do so WITHOUT writing to `respond_contacts.session_vars` (D14: dry run is side
  effect free). Before the fix, the ASK arm's `TurnResult(session_patch=None)` was
  unconditional, so `console_service._next_state` (which already reads a top-level
  `session_patch`) had nothing to read, and the clarify turn's pick landed with an
  empty carried session.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import DEFAULT_SUGGESTED_AGENT

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import (
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO, _link_contact_company, _seed_workspace
from tests.chatbot.test_rearch_s3_roster_from_resolver import (
    PRODUCT_CODES,
    _seed_products,
    _stub_incoming_probe,
)


@pytest.fixture()
def stub_access_spy(monkeypatch):
    """Like `test_engine.stub_access`, but records every `agent_code` check_access saw."""
    calls: list[str | None] = []

    def _install(allowed: bool = True, decision: str = "allow"):
        def fake_check_access(db, *, agent_code, contact_id, space_id):
            calls.append(agent_code)
            return {
                "allowed": allowed,
                "decision": decision,
                "agent_name": "General Enquiries",
                "attributes": None,
                "all_attributes_allowed": None,
            }

        monkeypatch.setattr(engine_mod, "check_access", fake_check_access)
        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")

    return _install, calls


def _no_agent_named_verdict(**overrides: Any) -> dict[str, Any]:
    routing = {"suggested_team": None, "suggested_agent": None, "team_source": None}
    routing.update(overrides.pop("routing_overrides", {}))
    return _parser_output(routing=routing, **overrides)


class TestFinding2bRoutingDefaultAppliedOnceBeforeAccess:
    """Contract line 58 (access agent fails closed) fails closed on the CONTACT's grant,
    never on a turn that simply named no agent."""

    def test_a_turn_naming_no_agent_is_checked_against_the_routing_default_not_none(
        self, session_factory, seeded, stub_parser, stub_access_spy
    ):
        install, calls = stub_access_spy
        stub_parser(_no_agent_named_verdict())
        install(allowed=True, decision="allow")

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert calls == [DEFAULT_SUGGESTED_AGENT]
        assert DEFAULT_SUGGESTED_AGENT is not None

    def test_a_contact_granted_the_default_agent_is_not_denied_for_an_unrouted_turn(
        self, session_factory, seeded, stub_parser, stub_access_spy
    ):
        install, calls = stub_access_spy
        stub_parser(_no_agent_named_verdict())
        install(allowed=True, decision="allow")

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind != "access_denied"
        assert calls == [DEFAULT_SUGGESTED_AGENT]

    def test_a_contact_not_granted_the_default_agent_is_still_denied(
        self, session_factory, seeded, stub_parser, stub_access_spy
    ):
        """The denial must trace to the contact's grant, not the defaulting itself."""
        install, calls = stub_access_spy
        stub_parser(_no_agent_named_verdict())
        install(allowed=False, decision="deny_no_access")

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "access_denied"
        assert result.item["decision"] == "deny_no_access"
        # Denied because of the grant, not because agent_code stayed null.
        assert calls == [DEFAULT_SUGGESTED_AGENT]


def _seed_top_level_session_vars(session_factory, state: dict) -> None:
    """Upsert the contact row with `session_vars = state` at the TOP LEVEL (the five
    session keys directly, no `variables` wrapper - `test_rearch_s3_journey_chain.py`
    module docstring, captain ruling 16 Sep 2026). Matches the real read/write shape
    `conversation_variables_service.get_for_contact` uses; `test_engine.py::seeded`
    writes the legacy `{"variables": {}}` shape instead, which this scenario (a real
    `narrow_to_code` roster) does not need.
    """
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb)) "
            "ON CONFLICT (phone_number) DO UPDATE SET session_vars = CAST(:sv AS jsonb)"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000010", "sv": json.dumps(state)},
    )
    db.commit()


def _read_session_vars(session_factory) -> dict:
    row = session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID)},
    ).first()
    return row.session_vars or {}


class TestFinding2aOpenPendingHandsBackSessionPatch:
    """A dry-run turn that opens a pending question (here: the `incoming` domain's
    product roster, contract 33/35 - the same shape hand-pass-1 finding 2a's chain
    used) carries it forward via `TurnResult.session_patch`, and writes nothing to
    `respond_contacts.session_vars` (D14) while doing so. Before the fix, `_run_answer`
    (the arm every `_ASK_BRANCH_KINDS` turn reaches) returned `session_patch=None`
    unconditionally, so a dry-run console turn that opened a roster had nothing for
    `console_service._next_state` to chain the next turn from.
    """

    def _roster_verdict(self, *, confident: bool = True) -> dict[str, Any]:
        return verdict(
            domain_hint="incoming",
            intent_hint="check_incoming",
            entities=[entity("wc286", hint="product", confident=confident)],
        )

    def test_a_dry_run_roster_turn_returns_a_non_null_session_patch(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ):
        # 17 Sep 2026, coder 20's landed change (`3c19a8533`): the private test DB
        # holds no WC286 product, so this bare "wc286" ask found nothing and fell
        # through to an unfiltered fetch attempt (the ONE-OPTION typed-token roster
        # this round retires) rather than arming the real `product_pick` roster this
        # test's docstring names. Seeds the exact family
        # `test_rearch_s3_roster_from_resolver.py` measures its own green result
        # against, and reads it with `confident=False` (a bare family word, not a
        # settled code - `turn/apply.py::_did_you_mean`'s own docstring): with the
        # family seeded, `_did_you_mean` defers to the narrower, which arms the real
        # ten-option roster instead of asking the typed word back.
        _seed_top_level_session_vars(session_factory, {})
        _link_contact_company(session_factory, company_id=SORENTO)
        _seed_products(session_factory, PRODUCT_CODES)
        _stub_incoming_probe(monkeypatch, codes_with_incoming=set())
        # Tester 36 (review round, 20 Sep 2026): `_seed_top_level_session_vars`'s bare
        # INSERT never sets `workspace_id`, so the real resolver's tier-1/2 lexical
        # match found nothing for "wc286" (falling through to a tier-3 embedding call
        # that raises for lack of an API key) - a TEST HARNESS gap, not the
        # architectural "this can never resolve here" limit coder 31's round report
        # claimed. Link a real workspace, same fix as
        # `test_rearch_s3_journey_chain.py::_seed_wc286_family`.
        workspace_id = _seed_workspace(session_factory)
        db = session_factory()
        db.execute(
            text("UPDATE respond_contacts SET workspace_id = :wid WHERE respond_io_id = :c"),
            {"wid": workspace_id, "c": str(CONTACT_ID)},
        )
        db.commit()
        stub_parser(self._roster_verdict(confident=False))
        stub_access()
        envelope = _envelope(test_run_id="ZZT-run-2a")
        assert envelope.dry_run is True

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        # The turn asked something (the product roster) - proven by `business_query`
        # (contract-line-33 shape, T1) plus the patch that lets the console chain it.
        assert result.branch_kind == "business_query", result.branch_kind
        assert result.session_patch is not None
        assert result.session_patch.get("open_question") is not None, result.session_patch
        open_question = result.session_patch["open_question"]
        assert open_question.get("kind") == "product_pick", open_question

        # Pin what this test's own docstring claims - a REAL ten-option roster of
        # the resolver's own candidates, never the retired one-option typed-token
        # echo (AC-1691/AC-1692, R6) this test was measured to be green on before.
        options = open_question.get("options") or []
        assert len(options) >= 2, (
            f"a require-specific roster must never be a single option: {open_question!r}"
        )
        labels = {opt.get("label") for opt in options}
        assert "wc286" not in {str(label).strip().lower() for label in labels}, (
            f"the roster must list the resolver's real candidate codes, never the "
            f"customer's own typed word back at them: {open_question!r}"
        )
        assert labels == set(PRODUCT_CODES), (
            f"the roster must be the full real family the resolver actually "
            f"matched: {open_question!r}"
        )

    def test_the_dry_run_writes_nothing_to_respond_contacts_session_vars(
        self, session_factory, stub_parser, stub_access
    ):
        _seed_top_level_session_vars(session_factory, {})
        stub_parser(self._roster_verdict())
        stub_access()
        before = _read_session_vars(session_factory)

        envelope = _envelope(test_run_id="ZZT-run-2a-d14")
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        after = _read_session_vars(session_factory)

        assert result.branch_kind == "business_query", result.branch_kind
        assert result.session_patch is not None
        assert after == before, "D14: a dry run must write nothing to respond_contacts"
