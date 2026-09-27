"""S3 parser schema + `history_question` routing - tester-first RED, from the UAC and
the lane A contract (section 6.5 "What the parser is asked to do with memory"), UPDATED
for the round 3 UAC (merged 5b110df8).

Covers AC-MEM033, AC-MEM069.

**Round 3 change, listed**: the parser output is RENAMED and RESHAPED - `profile_statement`
(a single nullable `{key, value}`) becomes `profile_statements`, a LIST of at most 3
`{key, value}` (AC-MEM033/AC-MEM069). A verdict may now state several facts on ONE turn
("stock SRTWB1455 for my Aurora project" answers the stock ask AND saves `project`, both
from the SAME verdict). Every test in `TestProfileStatementInSchema` and
`TestApplyDropsUnknownProfileStatementKey` that built a bare `profile_statement={...}` dict
is updated to `profile_statements=[{...}]`.

**Ruled by the coordinator, 26 Sep 2026**: the key enum is the SIX keys (`language, role,
usual_brands, usual_sites, project, about`), per the contract - `about` is a validated,
staff/stated-sourced vocabulary key in the contract's own section 4 table, and the plan's
ruling 4 in section 8 reads Q6 as "anything the dealer says about themselves". The
contract's own section 6.5 prose names only five (missing `about`); the six-key table in
section 4 (and AC-MEM069's own list) governs.

Postgres only where a test drives the full engine (`tests/chatbot/conftest.py::
session_factory`); the schema/`_lane` tests are pure and need no database.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from tests.chatbot._turn_helpers import build_policy, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401

MEMORY_STATEMENT_KEYS = {"language", "role", "usual_brands", "usual_sites", "project", "about"}


def _cid() -> str:
    return f"ZZT-schema-{uuid.uuid4().hex[:10]}"


def _seed_contact(session_factory, contact_respond_id: str) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_respond_id, "phone": f"+6011{uuid.uuid4().hex[:8]}", "sv": json.dumps({"variables": {}})},
    )
    db.commit()


# --------------------------------------------------------------------------- #
# AC-MEM033/AC-MEM069: the strict provider schema gains `profile_statements` (a
# LIST, at most 3) - `profile_statement` (singular) is RETIRED, round 3.
# --------------------------------------------------------------------------- #


class TestProfileStatementInSchema:
    def test_schema_declares_a_nullable_profile_statements_array_property(self) -> None:
        from app.services.chatbot.head import parser

        prop = parser.PARSE_OUTPUT_JSON_SCHEMA["properties"].get("profile_statements")
        assert prop is not None, (
            "PARSE_OUTPUT_JSON_SCHEMA must declare a nullable `profile_statements` "
            "array property, at most 3 {key, value} items (round 3, AC-MEM033/069)"
        )
        assert prop.get("maxItems") == 3, (
            f"profile_statements must cap at 3 items, got maxItems={prop.get('maxItems')!r}"
        )
        assert "profile_statements" in parser.PARSE_OUTPUT_JSON_SCHEMA["required"], (
            "strict mode (additionalProperties: false) requires every property to be "
            "declared `required`, exactly like `group_by`/`top_n`/`sales_channel`"
        )

    def test_the_old_singular_profile_statement_property_is_gone(self) -> None:
        from app.services.chatbot.head import parser

        assert "profile_statement" not in parser.PARSE_OUTPUT_JSON_SCHEMA["properties"], (
            "the singular `profile_statement` is retired (round 3) - `profile_statements` "
            "(a list) replaces it, not sits beside it"
        )

    def test_key_enum_is_exactly_six_memory_keys(self) -> None:
        """See module docstring's ambiguity note (six keys per the captain's brief,
        including `about`; the contract's own section 6.5 text lists five)."""
        from app.services.chatbot.head import parser

        prop = parser.PARSE_OUTPUT_JSON_SCHEMA["properties"].get("profile_statements") or {}
        item_schema = prop.get("items") or {}
        key_schema = ((item_schema.get("properties") or {}).get("key")) or {}
        enum = set(key_schema.get("enum") or [])
        assert enum == MEMORY_STATEMENT_KEYS, enum


# --------------------------------------------------------------------------- #
# message_type gains history_question, routed to the low_signal branch
# --------------------------------------------------------------------------- #


class TestHistoryQuestionRouting:
    def test_lane_routes_history_question_with_no_domain_to_casual(self) -> None:
        from app.services.chatbot.turn.apply import _lane

        policy = build_policy()
        v = verdict(message_type="history_question", domain_hint=None)
        lane = _lane(v, domains=[], policy=policy)
        assert lane == "casual", (
            f"a history_question turn must route to the SAME lane a casual/unknown "
            f"turn does (low_signal, no new route) - got {lane!r}"
        )

    def test_engine_turn_with_history_question_reaches_low_signal_branch(  # noqa: N802

        self, session_factory, stub_parser, stub_access
    ) -> None:
        """NOT red against today's code: `_lane` returns `None` for an unhandled
        `message_type` (see the unit test above, which IS red), and `None` still
        happens to reach a `low_signal`-labelled branch_kind through a different,
        coincidental engine path. Kept as a non-regression guard rather than
        silently relied on as evidence for AC-MEM069."""
        from app.services.chatbot import engine as engine_mod

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        stub_access()
        stub_parser(verdict(message_type="history_question", domain_hint=None, entities=[]))
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-schema-hq-1"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.branch_kind == "low_signal", (
            f"expected the low_signal branch for a history_question turn, got "
            f"{result.branch_kind!r}"
        )


# --------------------------------------------------------------------------- #
# APPLY drops any profile_statement key outside the vocabulary, with a trace line
# --------------------------------------------------------------------------- #


class TestApplyDropsUnknownProfileStatementKey:
    def test_an_out_of_vocabulary_key_is_dropped_and_traced(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from app.services.chatbot import engine as engine_mod

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        stub_access()
        # "tier" and "note" and "customer" are all OUTSIDE the profile_statements
        # vocabulary (contract 6.5 / this file's MEMORY_STATEMENT_KEYS) - a stated
        # write for any of them must be dropped, never silently written.
        stub_parser(verdict(
            domain_hint="inventory", entities=[],
            profile_statements=[{"key": "customer", "value": "Someone Else Sdn Bhd"}],
        ))
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-schema-drop-1"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        db = session_factory()
        stored = db.execute(
            text("SELECT chatbot_profile FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid}
        ).scalar()
        facts = (stored or {}).get("facts") or []
        assert not any(f.get("key") == "customer" for f in facts), (
            f"an out-of-vocabulary profile_statement key must never be written: {facts}"
        )

        from app.models.chatbot_turn import ChatbotTurn

        row = session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        trace_text = json.dumps(row.trace if row is not None else None)
        assert "customer" in trace_text and (
            "dropped" in trace_text.lower() or "rejected" in trace_text.lower() or "invalid" in trace_text.lower()
        ), (
            f"a dropped profile_statement must leave a trace line naming what was "
            f"rejected, found nothing in: {trace_text[:2000]}"
        )

    def test_more_than_three_statements_keeps_only_the_first_three(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        """AC-MEM033/069: `profile_statements` caps at 3 - a verdict naming four
        (however it got past the schema, e.g. a harness bypass) writes only the
        first three."""
        from app.services.chatbot import engine as engine_mod

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        stub_access()
        stub_parser(verdict(
            domain_hint="inventory", entities=[],
            profile_statements=[
                {"key": "role", "value": "purchaser"},
                {"key": "language", "value": "ms"},
                {"key": "project", "value": "Aurora"},
                {"key": "about", "value": "runs the Kuching site"},
            ],
        ))
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-schema-cap3-1"
        engine_mod.run_turn(envelope, session_factory=session_factory)

        db = session_factory()
        stored = db.execute(
            text("SELECT chatbot_profile FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid}
        ).scalar()
        facts = (stored or {}).get("facts") or []
        keys_written = {f.get("key") for f in facts}
        assert keys_written == {"role", "language", "project"}, (
            f"only the FIRST three statements must be written, got {keys_written}"
        )
        assert "about" not in keys_written


# --------------------------------------------------------------------------- #
# AC-MEM033: a business ask and a profile statement on the SAME turn both land
# --------------------------------------------------------------------------- #


class TestCombinedAskAndStatement:
    def test_stock_ask_with_a_project_statement_answers_stock_and_saves_project(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        from app.services.chatbot import engine as engine_mod

        cid = str(CONTACT_ID)
        _seed_contact(session_factory, cid)
        stub_access()
        stub_parser(verdict(
            domain_hint="inventory",
            entities=[{"raw": "SRTWB1455", "hint": "product", "canonical_code": "SRTWB1455",
                       "current_message": True, "confident": True, "hint_confident": True}],
            profile_statements=[{"key": "project", "value": "Aurora"}],
        ))
        envelope = _envelope()
        envelope.message["message"]["messageId"] = "ZZT-schema-combined-1"
        envelope.message["message"]["message"]["text"] = "stock SRTWB1455 for my Aurora project"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.branch_kind == "business_query", (
            f"the stock ask must still be answered as an ordinary business query, "
            f"got {result.branch_kind!r}"
        )

        db = session_factory()
        stored = db.execute(
            text("SELECT chatbot_profile FROM respond_contacts WHERE respond_io_id = :c"), {"c": cid}
        ).scalar()
        facts = (stored or {}).get("facts") or []
        project_fact = next((f for f in facts if f.get("key") == "project"), None)
        assert project_fact is not None and project_fact.get("value") == "Aurora", (
            f"the SAME turn's profile_statements must also be saved, got facts={facts}"
        )
