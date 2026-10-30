"""CHATBOT-SET-STOCK (owner answers 30 Oct 2026 on card v3): the resolver identifies a typed code
as a product set, with no parser prompt change, and the stock answer shows every member product of
the set in today's product format.

Production runs a parser version without the CODE LOOKUP section, so every engine test here runs
with `code_lookup` OFF. The live failure it pins: "Pls check stock srtwc7405 x 6 sets" answered only
SRTWC7405-SC and SRTWC7405-SC-UOA, because the resolver's tier-2 prefix probe matched products only
and the tank (SRTWCX...) and bowl (SRTWCY...) codes do not start with the typed code.

Synthetic codes keep the dev data's shape (crew rows, prod copy 20 Oct): nine 7405 sets that all
start with the catalogue code, two 8826 sets sharing the bowl and seat cover.
Card: documentation/plans/chatbot/CARD-chatbot-set-stock-30oct.md."""
from __future__ import annotations

from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from app.services import entity_resolver
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_code_lookup_set_codes import (  # noqa: F401
    _all_ids,
    _mk_products,
    _mk_set,
    _run,
    _scope_listeners,
    db,
)
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

STEM = "ZZSTWC7405"  # the catalogue code the salesperson typed; no product or set carries it
SETS_7405 = {
    "ZZSTWC7405-S": ("ZZSTWCX7405-S", "ZZSTWCY7405", "ZZSTWC7405-SC"),
    "ZZSTWC7405-RL-S-PJ": ("ZZSTWCX7405-RL-S-PJ", "ZZSTWCY7405-PJ", "ZZSTWC7405-SC"),
    "ZZSTWC7405-S-UOA": ("ZZSTWCX7405-S-UOA", "ZZSTWCY7405-UOA", "ZZSTWC7405-SC-UOA"),
}
STEM_8826 = "ZZSTWC8826"
SETS_8826 = {
    "ZZSTWC8826-P": ("ZZSTWCX8826-P", "ZZSTWCY8826", "ZZSTWC8826-SC"),
    "ZZSTWC8826-S": ("ZZSTWCX8826-S", "ZZSTWCY8826", "ZZSTWC8826-SC"),
}


def _codes(sets: dict[str, tuple[str, ...]]) -> list[str]:
    return sorted({c for members in sets.values() for c in members})


def _seed_sets(db, sets: dict[str, tuple[str, ...]], *, hidden: frozenset[str] = frozenset()) -> dict[str, str]:
    codes = _codes(sets)
    ids = _mk_products(db, [c for c in codes if c not in hidden])
    if hidden:
        ids.update(_mk_products(db, sorted(hidden), searchable=False))
    for set_code, members in sets.items():
        _mk_set(db, set_code, [ids[c] for c in members], name=f"Pedestal {set_code}")
    return ids


def _seed(session_factory, sets, **kw) -> dict[str, str]:
    db = session_factory()
    ids = _seed_sets(db, sets, **kw)
    db.commit()
    return ids


def _stock(session_factory, stub_access, monkeypatch, text: str, raw: str, canonical: str | None = None):
    return _run(
        session_factory, stub_access, monkeypatch, text=text, raw=raw, canonical=canonical,
        domain="inventory", intent="check_stock", code_lookup=False,
    )


def _stock_ids(calls) -> set[str]:
    return {
        pid for name, args in calls if name == "crm_inventory_stock_balance_list" for pid in (args.get("product_ids") or [])
    }


# ---------------------------------------------------------------- resolver


def _matches(db, token: str) -> list[Any]:
    result = entity_resolver.resolve_references(
        db, [token], allowed_entity_types=["product"], enable_embedding_fallback=False,
    )
    return [m for r in result.resolutions for m in r.matches]


def test_resolver_a_catalogue_code_resolves_to_every_set_that_starts_with_it(db):
    _seed_sets(db, SETS_7405)

    sets = {m.canonical_code for m in _matches(db, STEM.lower()) if m.entity_type == "product_set"}

    assert sets == set(SETS_7405), sets


def test_resolver_a_set_found_by_its_catalogue_code_carries_its_members(db):
    _seed_sets(db, SETS_8826)

    found = {m.canonical_code: m for m in _matches(db, STEM_8826.lower()) if m.entity_type == "product_set"}

    assert set(found) == set(SETS_8826), found
    for set_code, members in SETS_8826.items():
        assert [x["product_code"] for x in found[set_code].display["members"]] == list(members)


def test_resolver_an_inactive_set_is_not_found_by_its_catalogue_code(db):
    ids = _mk_products(db, list(SETS_8826["ZZSTWC8826-P"]))
    _mk_set(db, "ZZSTWC8826-P", list(ids.values()), active=False)

    assert not [m for m in _matches(db, STEM_8826.lower()) if m.entity_type == "product_set"]


def test_resolver_a_full_product_code_still_resolves_to_that_product_only(db):
    """Control: SRTWC7405-SC typed in full is the seat cover (and today's variant siblings, such as
    -SC-UOA), never its sets and never a tank or bowl."""
    _seed_sets(db, SETS_7405)

    matches = _matches(db, "zzstwc7405-sc")

    assert {m.entity_type for m in matches} == {"product"}, [(m.entity_type, m.canonical_code) for m in matches]
    assert "ZZSTWC7405-SC" in {m.canonical_code for m in matches}
    assert not {m.canonical_code for m in matches} & {"ZZSTWCX7405-S", "ZZSTWCY7405"}


# ---------------------------------------------------------------- engine, CODE LOOKUP off


def test_the_7405_ask_fetches_tank_bowl_and_seat_cover_of_every_set(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, SETS_7405)

    _text, calls = _stock(session_factory, stub_access, monkeypatch, f"Pls check stock {STEM.lower()} x 6 sets", STEM.lower())

    assert _stock_ids(calls) == set(ids.values()), sorted(_stock_ids(calls))


def test_the_7405_answer_names_each_set(session_factory, seeded, stub_access, monkeypatch):
    _seed(session_factory, SETS_7405)

    text, _calls = _stock(session_factory, stub_access, monkeypatch, f"stock {STEM.lower()}", STEM.lower())

    for set_code in SETS_7405:
        assert set_code in text, text


def test_the_8826_ask_fetches_both_tanks_the_shared_bowl_and_the_seat_cover(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, SETS_8826)

    _text, calls = _stock(session_factory, stub_access, monkeypatch, f"stock {STEM_8826.lower()}", STEM_8826.lower())

    assert _stock_ids(calls) == {ids[c] for c in _codes(SETS_8826)}, sorted(_stock_ids(calls))


def test_an_exact_set_code_answers_its_members_with_code_lookup_off(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, SETS_8826)

    text, calls = _stock(
        session_factory, stub_access, monkeypatch, "stock ZZSTWC8826-S", "ZZSTWC8826-S", canonical="ZZSTWC8826-S",
    )

    assert _stock_ids(calls) == {ids[c] for c in SETS_8826["ZZSTWC8826-S"]}, sorted(_stock_ids(calls))
    assert "ZZSTWC8826-S" in text, text


def test_a_set_with_a_member_hidden_from_chat_is_not_expanded(session_factory, seeded, stub_access, monkeypatch):
    """A member the contact may not see hides its whole set (today's visibility rule); the stem
    still answers the visible products that start with it, never the hidden part."""
    ids = _seed(session_factory, SETS_8826, hidden=frozenset({"ZZSTWCX8826-P"}))

    _text, calls = _stock(session_factory, stub_access, monkeypatch, f"stock {STEM_8826.lower()}", STEM_8826.lower())

    fetched = _stock_ids(calls)
    assert ids["ZZSTWCX8826-P"] not in fetched, sorted(fetched)
    assert {ids[c] for c in SETS_8826["ZZSTWC8826-S"]} <= fetched, sorted(fetched)


def test_a_member_code_typed_in_full_answers_that_product_only(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, SETS_7405)

    _text, calls = _stock(
        session_factory, stub_access, monkeypatch, "stock ZZSTWC7405-SC", "ZZSTWC7405-SC", canonical="ZZSTWC7405-SC",
    )

    assert ids["ZZSTWC7405-SC"] in _stock_ids(calls)
    assert ids["ZZSTWCX7405-S"] not in _stock_ids(calls), sorted(_stock_ids(calls))


@pytest.fixture(autouse=True)
def _no_code_lookup_prompt(monkeypatch):
    """Belt and braces: nothing here may depend on the CODE LOOKUP prompt being published."""
    monkeypatch.setattr(parser_mod, "uses_code_lookup", lambda *a, **k: False)
