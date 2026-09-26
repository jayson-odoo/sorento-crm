"""Reviewer pass on PR #833 round 5 at 34cb4697 (26 Sep 2026): B1-r5 and N-r5-2 and N-r5-3.
N-r5-1 is in the brands vitest.

Every test here failed on 34cb4697e for the scenario the reviewer named; the replay of the
owner's eight exchanges (round 4) and the round 5 B1 tests stay green beside them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.chatbot.test_attribute_asks_round2 import _product
from tests.chatbot.test_attribute_asks_round4 import (  # noqa: F401 - fixtures used by name
    _product_ask,
    chat,
    world,
)
from tests.chatbot.test_attribute_asks_round3 import world as r3world  # noqa: F401 - round 4's world builds on it
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name
from tests.chatbot.test_reverse_asks_owner_phrasings import _class_category

EIGHT = "I don't know 't trap' as a trap. I know P trap and S trap."

# --------------------------------------------------------------------------- #
# B1-r5: a product names a phrase only as whole words                           #
# --------------------------------------------------------------------------- #

#: (name, noun) pairs where "t trap" is a SUBSTRING of the name or the description
#: ("baskeT TRAP", "outleT TRAP", "buckeT TRAP") but never a whole-word phrase.
SUBSTRING_PRODUCTS = (
    ("Floor Waste With Basket Trap", "FLOOR WASTE"),
    ("Floor Waste Z1", "FLOOR WASTE OUTLET TRAP"),
    ("Floor Waste Z2", "FLOOR WASTE BUCKET TRAP"),
)


def _add(world, name: str, noun: str):
    db = world["db"]
    row = _product(
        db,
        brand_id=world["sorento"].id,
        category_id=_class_category(db, "FT"),
        uom_id=world["srt_tubs"][0].base_uom_id,
        noun=noun,
        prefix="ZZR6T",
        name=name,
    )
    db.commit()
    return row


@pytest.mark.parametrize("name,noun", SUBSTRING_PRODUCTS)
def test_b1r5_a_word_ending_in_t_before_trap_does_not_name_t_trap(world, name, noun):
    from app.services.product_spec_search import unknown_spec_values

    _add(world, name, noun)
    assert [u["said"] for u in unknown_spec_values(world["db"], "any water clost t trap?")] == ["t trap"]


def test_b1r5_exchange_8_stays_exact_beside_a_basket_trap(chat, world):
    """The reviewer's reproduction: the round 4 world plus one "Basket Trap" product."""
    _add(world, *SUBSTRING_PRODUCTS[0])
    text = chat.say("any water clost t trap?", _product_ask("water clost t trap", "any water closet t trap"))
    assert text == EIGHT, text


def test_b1r5_a_product_named_with_the_whole_phrase_is_still_searched(world):
    """The guard the word match keeps: "T Trap" as its own words in a name or a
    description is that product, not an unknown value."""
    from app.services.product_spec_search import unknown_spec_values

    _add(world, "Sorento T Trap Water Closet", "WATER CLOSET")
    assert unknown_spec_values(world["db"], "any water clost t trap?") == []


def test_b1r5_a_phrase_in_a_description_as_whole_words_is_searched(world):
    from app.services.product_spec_search import unknown_spec_values

    _add(world, "Floor Waste Z3", "FLOOR WASTE Q TRAP")
    assert unknown_spec_values(world["db"], "any q trap floor waste") == []


# --------------------------------------------------------------------------- #
# N-r5-2: an acronym word keeps its capitals inside a multi-word value          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,named",
    [
        ("PVC pipe", "PVC pipe"),
        ("LED white", "LED white"),
        ("Matt black", "matt black"),
        ("PVC", "PVC"),
        ("Gunmetal", "gunmetal"),
    ],
)
def test_n_r5_2_a_multi_word_value_keeps_its_acronym(value, named):
    from app.services.chatbot.lanes.business.answer import near_miss_sentence

    near = {"class_labels": ["Wash basin"], "label": "Material", "value": value, "other_total": 0}
    text = near_miss_sentence(near, {"incoming": True})
    assert text.startswith(f"No {named} wash basins with incoming stock"), text


# --------------------------------------------------------------------------- #
# N-r5-3: the console cases cover all six reviewer phrases, on any dead end     #
# --------------------------------------------------------------------------- #

REVIEWER_PHRASES = (
    "any deck mounted bath mixer",
    "which long spout basin tap has stock",
    "ceiling mounted shower",
    "rain shower ceiling mount",
    "any grease trap",
    "any click clack waste",
)


def _cases() -> list[dict[str, Any]]:
    import yaml

    path = Path(__file__).resolve().parent / "console_cases" / "2026-09-11-attribute-first-asks.yaml"
    body = yaml.safe_load(path.read_text())
    return body["cases"] if isinstance(body, dict) else body


@pytest.mark.parametrize("phrase", REVIEWER_PHRASES)
def test_n_r5_3_each_reviewer_phrase_has_a_console_case_refusing_any_dead_end(phrase):
    found = [c for c in _cases() if c.get("text") == phrase]
    assert found, f"no console case sends {phrase!r}"
    for case in found:
        assert "I don't know" in (case.get("expect") or {}).get("reply_not_contains", []), case
