"""S3 - profile hints rendered on every parse (AC-1548, PLAN-chatbot-turn-rearch.md
"State: three shelves" - `respond_contacts.chatbot_profile` JSONB, already committed
S0; parser hints, tier narrower).

`turn/memory.py::profile_block(profile) -> str` does not exist yet, so every test is
RED at collection with `ModuleNotFoundError: No module named 'app.services.chatbot.
turn.memory'`.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

# Forces collection failure now - see module docstring.
from app.services.chatbot.turn.memory import profile_block  # noqa: F401

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser


def _seed_with_profile(session_factory, *, profile: dict) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, "
            "chatbot_profile) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), CAST(:p AS jsonb))"
        ),
        {
            "cid": str(CONTACT_ID),
            "phone": "+60000000005",
            "sv": json.dumps({"variables": {}}),
            "p": json.dumps(profile),
        },
    )
    db.commit()


class TestProfileBlockDirect:
    def test_profile_block_carries_tier_language_default_ledgers(self) -> None:
        from app.services.chatbot.turn.memory import profile_block
        from app.services.chatbot.turn.state import Profile

        profile = Profile(tier="dealer", language="en", default_ledgers=["IBORN"])
        block = profile_block(profile)

        assert "Profile:" in block
        assert "dealer" in block
        assert "en" in block
        assert "IBORN" in block


class TestProfileOnEveryParserUserBlock:
    def test_user_block_carries_profile_section(self, session_factory, stub_parser, stub_access) -> None:
        _seed_with_profile(session_factory, profile={"tier": "dealer", "language": "en", "default_ledgers": []})
        stub_access()

        user_blocks: list[str] = []

        def on_call(user_block: str) -> None:
            user_blocks.append(user_block)

        stub_parser(verdict(), on_call=on_call)

        from app.services.chatbot import engine as engine_mod

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert user_blocks, "the parser was never called"
        assert "Profile:" in user_blocks[0], user_blocks[0]

    def test_known_tier_suppresses_the_tier_question(self, session_factory, stub_parser, stub_access) -> None:
        _seed_with_profile(session_factory, profile={"tier": "dealer", "language": "en", "default_ledgers": []})
        stub_access()

        v = verdict(domain_hint="promotion", entities=[])
        stub_parser(v)

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind != "tier_ask", (
            f"a known profile tier must suppress the tier question, got "
            f"branch_kind={result.branch_kind!r}"
        )

    def test_fetch_filter_carries_the_known_tier(self, session_factory, stub_parser, stub_access, monkeypatch) -> None:
        _seed_with_profile(session_factory, profile={"tier": "dealer", "language": "en", "default_ledgers": []})
        stub_access()

        captured_filters: list[dict] = []

        def fake_run_fetch(plan, ctx):
            for spec in plan.fetch:
                captured_filters.append(spec.filters)
            return []

        from app.services.chatbot.turn import fetch as fetch_mod  # RED here too (fetch.py)

        monkeypatch.setattr(fetch_mod, "run_fetch", fake_run_fetch, raising=False)

        v = verdict(domain_hint="promotion", entities=[])
        stub_parser(v)

        from app.services.chatbot import engine as engine_mod

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert any(f.get("tier") == "dealer" for f in captured_filters), captured_filters
