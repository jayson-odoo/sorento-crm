"""S6 - the deletions guard (AC-1594, PLAN-chatbot-turn-rearch.md "Turn replay (the
gate)", "APPLY contract").

RED until the coder deletes every constant named below. Each is asserted GONE by
`getattr(module, name, _MISSING) is _MISSING` rather than a bare `hasattr` negation,
so a future reader sees exactly which name the assertion is about in a failure
message, and `_MISSING` (not `None`) so a constant some other change legitimately
sets to `None` is never mistaken for "deleted".

Replaces the S0 guardrail this same commit retires
(`tests/chatbot/test_rearch_s0_domains_seed.py`, every test in it importing
`DOMAIN_SPEC`/`SUGGESTED_TEAMS` and asserting the seeded `chatbot_domains` /
`chatbot_entity_kinds` tables equal the constant - plan's own words, "until the
constants are deleted (S6), a test asserts table == constant"). That guardrail's job
was to prove the table and the constant never drifted WHILE both existed; once the
constant is gone there is nothing left to drift against, and the rule this file
polices - the constant actually being gone - supersedes it.
"""
from __future__ import annotations

from typing import Any

_MISSING = object()


def _gone(module: Any, name: str) -> None:
    assert getattr(module, name, _MISSING) is _MISSING, (
        f"{module.__name__}.{name} still exists - AC-1594 requires it deleted once the "
        "table it was ported to (chatbot_domains / chatbot_entity_kinds / "
        "system_settings.chatbot_tier_order) is the only source"
    )


class TestContractsModuleDeletions:
    """`DOMAIN_SPEC` and every dict derived from it (`contracts.py`'s own "views over
    DOMAIN_SPEC" section), plus `SUGGESTED_TEAMS` - all superseded by the
    `chatbot_domains` table + `Policy` object (PLAN "The policy" section)."""

    def test_domain_spec_deleted(self) -> None:
        from app.services.chatbot import contracts

        _gone(contracts, "DOMAIN_SPEC")

    def test_bare_entity_type_by_domain_deleted(self) -> None:
        from app.services.chatbot import contracts

        _gone(contracts, "BARE_ENTITY_TYPE_BY_DOMAIN")

    def test_domain_switch_words_deleted(self) -> None:
        from app.services.chatbot import contracts

        _gone(contracts, "DOMAIN_SWITCH_WORDS")

    def test_default_unsupported_domains_deleted(self) -> None:
        from app.services.chatbot import contracts

        _gone(contracts, "DEFAULT_UNSUPPORTED_DOMAINS")

    def test_domain_claimed_tools_deleted(self) -> None:
        from app.services.chatbot import contracts

        _gone(contracts, "DOMAIN_CLAIMED_TOOLS")

    def test_suggested_teams_deleted(self) -> None:
        from app.services.chatbot import contracts

        _gone(contracts, "SUGGESTED_TEAMS")


class TestFetchModuleDeletions:
    """`lanes/business/fetch.py`'s three constants ported to the policy tables."""

    def test_base_property_words_deleted(self) -> None:
        from app.services.chatbot.lanes.business import fetch

        _gone(fetch, "_BASE_PROPERTY_WORDS")

    def test_tier_order_deleted(self) -> None:
        from app.services.chatbot.lanes.business import fetch

        _gone(fetch, "TIER_ORDER")

    def test_entity_filter_required_tools_deleted(self) -> None:
        from app.services.chatbot.lanes.business import fetch

        _gone(fetch, "ENTITY_FILTER_REQUIRED_TOOLS")

    def test_product_id_required_tools_deleted(self) -> None:
        from app.services.chatbot.lanes.business import fetch

        _gone(fetch, "PRODUCT_ID_REQUIRED_TOOLS")


class TestTierOrderOtherTwoCopiesDeleted:
    """The plan names THREE `TIER_ORDER` copies (`fetch.py`'s is asserted above):
    `tier_gate.py`'s own literal, and `turn/policy_rows.py::DEFAULT_TIER_ORDER` (the
    fallback `policy.py` reads when `system_settings.chatbot_tier_order` is unset).
    All three collapse onto the ONE column."""

    def test_tier_gate_tier_order_deleted(self) -> None:
        from app.services.chatbot.lanes.business import tier_gate

        _gone(tier_gate, "TIER_ORDER")

    def test_policy_rows_default_tier_order_deleted(self) -> None:
        from app.services.chatbot.turn import policy_rows

        _gone(policy_rows, "DEFAULT_TIER_ORDER")
