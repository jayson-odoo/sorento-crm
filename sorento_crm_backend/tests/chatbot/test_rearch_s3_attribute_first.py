"""S3 - attribute-first asks, ported (AC-1534, PLAN-chatbot-turn-rearch.md contract 114
to 120, "#833").

Source read for this port: `origin/feat/chatbot-attribute-first-asks` (never merged,
commit 34f88114f). **Ambiguity flagged to the captain**: the brief named
`tests/chatbot/test_attribute_first_*.py` on that branch as a second source; no such
files exist there (`git ls-tree -r origin/feat/chatbot-attribute-first-asks --name-only
| grep -i attribute` returns only the console yaml, a migration test and doc files) -
this file is ported from the console yaml
(`sorento_crm_backend/tests/chatbot/console_cases/2026-09-11-attribute-first-asks.yaml`
on that branch) alone, read via `git show`, never imported across branches.

Every test is RED at collection with `ModuleNotFoundError: No module named
'app.services.chatbot.turn.compose'` (same whole-file mechanism as
`test_rearch_s3_team_pick_and_866.py` - see that file's docstring for why this is the
right reason rather than a live run against the un-rewired engine).

**Ambiguity flagged to the captain**: the parser's carrier for an attribute-first ask
is assumed to be v3's already-declared `requested_attributes: list[str]` key
(`tests.chatbot._turn_helpers.verdict`'s own default, `[]`) plus `domain_hint` /
`entities[].hint` naming the class word's resolved kind - no other key exists in the
v3 schema for this. The exact reply grammar ("N <kind> have <attribute>. Showing 5.")
and the paging window (5 per page, "Showing 6 to 10" on a second "more") are copied
from the console yaml's own `reply_contains` assertions, not invented.
"""
from __future__ import annotations

from typing import Any

import pytest

# Forces collection failure now - see module docstring.
from app.services.chatbot.turn.compose import Answer  # noqa: F401

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser


def _seed(session_factory) -> None:
    import json

    from sqlalchemy import text

    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000002", "sv": json.dumps({"variables": {}})},
    )
    db.commit()


class TestCountedSetAnswer:
    """Console case "a class word scopes the set and the header counts it" (AC-1306,
    AC-1316): "which tap has cert" -> "taps have certificates ... Showing 5"."""

    def test_counted_answer_names_kind_attribute_and_shows_five(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed(session_factory)
        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["certificate"],
            entities=[entity("tap", hint="product_type", confident=True)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert "have certificates" in text or "certificate" in text.lower(), text
        assert "Showing 5" in text, text


class TestPagingByFive:
    def test_more_pages_the_same_set_by_five(self, session_factory, stub_parser, stub_access) -> None:
        _seed(session_factory)
        offsets_seen: list[int] = []

        def on_call(user_block: str) -> None:
            offsets_seen.append(len(offsets_seen))

        v1 = verdict(
            domain_hint="product_attachment",
            requested_attributes=["certificate"],
            entities=[entity("tap", hint="product_type", confident=True)],
        )
        stub_parser(v1, on_call=on_call)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        first = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert "Showing 5" in (first.reply or {}).get("text", ""), first.reply

        v2 = verdict(message_type="clarification", user_goal="more")
        stub_parser(v2, on_call=on_call)
        second_envelope = _envelope()
        second_envelope.message["message"]["messageId"] = "ZZT-attr-first-page-2"
        second_envelope.message["message"]["message"]["text"] = "more"
        second = engine_mod.run_turn(second_envelope, session_factory=session_factory)

        assert "Showing 6 to 10" in (second.reply or {}).get("text", ""), second.reply


class TestOwnCompanyCertificatesOnly:
    def test_certificates_filter_to_the_contacts_own_company(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed(session_factory)
        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["certificate"],
            entities=[entity("SRTWT5875", hint="product", confident=True)],
        )
        stub_parser(v)
        stub_access(attributes=["product_attachment.certificate"])

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query", result.branch_kind


class TestTierVisiblePromotionsOnly:
    def test_promotion_count_respects_tier_visibility(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed(session_factory)
        v = verdict(
            domain_hint="promotion",
            requested_attributes=["promotion"],
        )
        stub_parser(v)
        stub_access(attributes=["promotion.view"])

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query", result.branch_kind


class TestUnknownAttributeClarify:
    """Console case "an unknown class word clarifies with the nearest label" (AC-1320):
    "which water tap has cert" -> "I don't know 'water tap'", "Did you mean"."""

    def test_unknown_attribute_word_clarifies_naming_valid_schemes(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed(session_factory)
        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["cert"],
            entities=[entity("water tap", hint="product_type", confident=False)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert "don't know" in text.lower() or "did you mean" in text.lower(), text


class TestAnyXIncomingLeg:
    """Console case "the incoming leg" (AC-1311): "which sink has incoming" -> "kitchen
    sinks have incoming stock"."""

    def test_any_x_incoming_routes_to_incoming_section(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed(session_factory)
        v = verdict(
            domain_hint="incoming",
            requested_attributes=["incoming"],
            entities=[entity("sink", hint="product_type", confident=True)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert "incoming" in text.lower(), text
