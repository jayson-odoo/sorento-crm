"""AND-ROW-REGISTRY (CHAT-CLOSED-LISTS round 9, R9-1 / R9-2): the gate `_drop_word_code_fragments`
checks the registry over EVERY token of an AND row on both code branches. "basin" is a registry word
(a Basin class), "bidet" is not: the row ZZBASIN-BIDET reached the answer through its code only, so a
registry word inside it must not ride on the non-registry segment "bidet"."""
from __future__ import annotations

import pytest

from app.api.v1.system.references import _drop_word_code_fragments
from app.models.product import ProductCategory
from app.models.product_spec import ProductSpecRegistry
from tests.test_resolve_predicate import ENDPOINT, _product_codes, _stocked, client, db  # noqa: F401 - fixtures by name


def _and_row(code: str) -> dict:
    return {"entity_type": "product", "match_tier": "and", "uuid": f"u-{code}", "canonical_code": code}


def _gate(tokens: list[str], codes: list[str], vocabulary: set[str]) -> list[str]:
    result = {"tokens": tokens, "intersection": [_and_row(c) for c in codes]}
    _drop_word_code_fragments(result, frozenset(vocabulary))
    return [m["canonical_code"] for m in result["intersection"]]


def test_r9_1_unit_a_registry_word_inside_an_and_row_drops_it_though_the_other_segment_is_not_one():
    """RED today: the segment branch asks the registry only about "bidet" (a whole segment)."""
    assert _gate(["basin", "bidet"], ["ZZBASIN-BIDET"], {"basin"}) == []


def test_r9_2_unit_guards():
    # neither word in the registry: a code family, kept
    assert _gate(["qams", "bidet"], ["QAMS-BIDET"], {"basin"}) == ["QAMS-BIDET"]
    # one token, a non-registry word whole in the code: kept
    assert _gate(["bidet"], ["ACC-BIDET"], {"basin"}) == ["ACC-BIDET"]
    # a whole typed code, separators aside: kept even when its words are registry words
    assert _gate(["zzbasinbidet"], ["ZZBASIN-BIDET"], {"zzbasinbidet"}) == ["ZZBASIN-BIDET"]
    # a token with a digit keeps its fragment rows
    assert _gate(["basin", "wc286"], ["BASINWC286X"], {"basin"}) == ["BASINWC286X"]


def _basin_class(db) -> None:
    """The world's registry knows "basin" (a Basin class) and NOT "bidet": the seeded spec registry
    carries bidet words, so it is switched off; the class vocabulary alone answers."""
    db.query(ProductSpecRegistry).update({ProductSpecRegistry.is_active: False})
    db.add(ProductCategory(
        id="00000000-0000-4000-8000-00000000b451", category_code="ZZT-BASIN", category_name="ZZT Basin",
        class_label="basin", is_searchable=True,
    ))
    db.flush()


def _post(client, tokens: list[str]) -> dict:
    return client.post(
        ENDPOINT,
        json={
            "query": " ".join(tokens), "tokens": tokens, "raw_tokens": tokens, "match_mode": "and",
            "spec_fallback": True, "exact_match": True, "fallback_to_all_types": True, "understand_phrase": False,
        },
    ).json()


def test_r9_1_route_an_and_row_holding_a_registry_word_is_not_a_hit(client, db):
    """RED today through the real route: ["basin", "bidet"] AND probes ZZBASIN-BIDET (tier "and")."""
    _stocked(db, "ZZBASIN-BIDET", "ZZT Bidet Spray", "BIDET SPRAY SET")
    _basin_class(db)  # after the product: `_stocked` takes an unordered first category

    payload = _post(client, ["basin", "bidet"])

    assert "ZZBASIN-BIDET" not in _product_codes(payload), payload


def test_r9_2_route_guards_a_non_registry_family_and_a_lone_word_stay_hits(client, db):
    _stocked(db, "ZZQAMS-BIDET", "ZZT Bidet Spray", "BIDET SPRAY SET")
    _stocked(db, "ZZACC-BIDET", "ZZT Bidet Acc", "BIDET ACCESSORY")
    _basin_class(db)

    assert "ZZQAMS-BIDET" in _product_codes(_post(client, ["zzqams", "bidet"]))
    assert "ZZACC-BIDET" in _product_codes(_post(client, ["bidet"]))


def test_r9_3_unit_a_plural_of_a_registry_word_drops_the_and_row():
    """RED: the AND probe matches "basins" by its singular too; the registry check reads it as typed."""
    assert _gate(["basins", "bidet"], ["ZZBASIN-BIDET"], {"basin"}) == []


def test_r9_3_unit_guard_plural_non_registry_words_stay_kept():
    assert _gate(["zzqams", "bidets"], ["ZZQAMS-BIDET"], {"basin"}) == ["ZZQAMS-BIDET"]


def test_r9_3_route_a_plural_registry_word_in_an_and_row_is_not_a_hit(client, db):
    _stocked(db, "ZZBASIN-BIDET", "ZZT Bidet Spray", "BIDET SPRAY SET")
    _basin_class(db)

    assert "ZZBASIN-BIDET" not in _product_codes(_post(client, ["basins", "bidet"]))


def test_r9_3_route_guard_plural_non_registry_words_stay_hits(client, db):
    _stocked(db, "ZZQAMS-BIDET", "ZZT Bidet Spray", "BIDET SPRAY SET")
    _basin_class(db)

    assert "ZZQAMS-BIDET" in _product_codes(_post(client, ["zzqams", "bidets"]))
