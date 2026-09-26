"""S0 - `chatbot_entity_kinds` seeded from `ENTITY_HINTS` + product's base property words
(AC-1502, PLAN-chatbot-turn-rearch.md).

Same substrate discipline as `test_rearch_s0_domains_seed.py`: real migrated DB, not a
`create_all` scratch schema, because the rows are migration-seeded data. See that file's
docstring for the full reasoning; not repeated here.

Tier order (captain ruling, 16 Sep 2026): NOT a `chatbot_entity_kinds` row - `tier` is
not one of the 12 `ENTITY_HINTS` and never gets a row. It is the new
`system_settings.chatbot_tier_order` JSONB column, defaulting to the code's own literal
order (`lanes/business/tier_gate.TIER_ORDER`, `("dealer", "office", "end_user")`). That
column is a plain model addition (like `chatbot_crossdomain_ladder`), not migration-only
seed DATA, so its test runs on the ordinary blank scratch schema.

RIGHT NOW every test here is RED: `chatbot_entity_kinds` does not exist, and
`system_settings` has no `chatbot_tier_order` column.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy import text

from app.services.chatbot.contracts import ENTITY_HINTS
from app.services.chatbot.turn.policy_rows import PRODUCT_BASE_PROPERTY_WORDS
from tests._pg_fixture import blank_session, pg_session

# AC-1592: `lanes.business.fetch._BASE_PROPERTY_WORDS` no longer exists (AC-1594) -
# `turn/policy_rows.py::PRODUCT_BASE_PROPERTY_WORDS` is its replacement, and already
# carries "discontinued"/"brand" natively (the old constant didn't, hence the union
# this file used to need).
EXPECTED_PRODUCT_WORDS = set(PRODUCT_BASE_PROPERTY_WORDS)


@pytest.fixture(scope="module")
def rows():
    with pg_session() as db:
        try:
            result = db.execute(text("SELECT * FROM chatbot_entity_kinds")).mappings().all()
        except ProgrammingError as exc:
            pytest.fail(
                f"chatbot_entity_kinds does not exist yet (AC-1502 migration not written): {exc}",
                pytrace=False,
            )
        yield {row["kind"]: dict(row) for row in result}


def test_exactly_the_12_entity_hints_kinds(rows):
    assert set(rows) == set(ENTITY_HINTS), rows.keys()


@pytest.mark.parametrize("kind", list(ENTITY_HINTS))
def test_every_kind_has_resolver_source_and_did_you_mean_and_default_narrowing(rows, kind):
    row = rows[kind]
    assert row.get("resolver_source"), row
    assert row.get("did_you_mean") in (True, False), row
    assert row.get("default_narrowing"), row


def test_product_base_property_words_cover_fetch_list_plus_discontinued_and_brand(rows):
    words = rows["product"].get("base_property_words") or {}
    assert isinstance(words, dict), words
    assert EXPECTED_PRODUCT_WORDS <= set(words), (EXPECTED_PRODUCT_WORDS - set(words), words)


def test_discontinued_maps_to_is_discontinued_column(rows):
    words = rows["product"].get("base_property_words") or {}
    assert words.get("discontinued") == "is_discontinued", words


def test_brand_word_is_mapped_to_some_column(rows):
    words = rows["product"].get("base_property_words") or {}
    assert words.get("brand"), words


def test_no_tier_row_in_chatbot_entity_kinds(rows):
    """Captain ruling: tier order is a system setting, not an entity-kind row."""
    assert "tier" not in rows, rows.keys()


def test_chatbot_tier_order_system_setting_defaults_to_tier_gate_literal():
    """AC-1592: the module-level `tier_gate.TIER_ORDER` constant is gone (AC-1594);
    `tier_gate._tier_order()` now reads `turn.policy.default_policy().tier_order`
    instead, the frozen seed `policy_rows.py::DEFAULT_TIER_ORDER` provides."""
    from app.models.user import SystemSetting
    from app.services.chatbot.lanes.business.tier_gate import _tier_order

    with blank_session() as db:
        row = SystemSetting()
        db.add(row)
        db.flush()
        value = db.execute(
            text("SELECT chatbot_tier_order FROM system_settings WHERE id = :i"),
            {"i": row.id},
        ).scalar()
        assert list(value or []) == list(_tier_order())


@pytest.mark.parametrize("kind", [k for k in ENTITY_HINTS if k != "product"])
def test_non_product_kinds_carry_family_grouping_or_none(rows, kind):
    # No hard expectation on the VALUE (only `customer` and `product` are named in the
    # UAC's family grouping examples) - only that the column exists and reads cleanly.
    row = rows[kind]
    assert "family_grouping" in row


def test_customer_family_grouping_is_ledger_family(rows):
    assert rows["customer"].get("family_grouping") == "ledger_family"


def test_product_family_grouping_is_base_code(rows):
    assert rows["product"].get("family_grouping") == "base_code"
