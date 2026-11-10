"""SORENTO-TOWN Phase 0: `redact()` (AC-3) and `strip_names()` (AC-4). Pure functions, no database.

Kill test: leave `shops[].ninety_day_amount` in `redact()` and `test_redact_*` goes red.
"""
from __future__ import annotations

import json

from tests.town._town_seed import AMOUNT_KEYS, FAKE_RM_FIGURES, all_keys, deep, fake_full


def test_redact_removes_every_amount_key_and_every_rm_figure():
    from app.services.town.snapshot import redact

    full = fake_full()
    assert AMOUNT_KEYS <= all_keys(full)  # the fixture does carry them, so the test can fail
    out = redact(full)
    assert not (all_keys(out) & AMOUNT_KEYS)
    text = json.dumps(out)
    for figure in FAKE_RM_FIGURES:
        assert figure not in text


def test_redact_keeps_counts_and_everything_else():
    from app.services.town.snapshot import redact

    full = fake_full()
    out = redact(full)
    assert out["today"] == {"invoice_count": 321, "credit_note_count": 2, "customer_count": 140}
    assert [s["today_docs"] for s in out["shops"]] == [3, 0, 1]
    assert [s["kind"] for s in out["shops"]] == ["shop", "shop", "stall"]
    assert [s["account_label"] for s in out["shops"]] == ["A/C II", None, None]
    assert out["warehouses"] == full["warehouses"]
    assert out["reorder"] == full["reorder"]
    assert out["approvals"] == full["approvals"]
    assert out["schema"] == 1 and out["phase"] == "day" and out["day"] == full["day"]


def test_redact_hides_dealer_identity_and_ranking_and_every_customer_id():
    from app.services.town.snapshot import redact

    full = fake_full()
    out = redact(full)
    for shop in out["shops"]:
        assert not ({"name", "code", "rank"} & set(shop))
    _assert_opaque([s["key"] for s in out["shops"]])
    text = json.dumps(out)
    for shop in full["shops"]:
        assert shop["key"] not in text and shop["name"] not in text and shop["code"] not in text
    # the full variant carries all of it
    assert {"name", "code", "rank", "key"} <= set(full["shops"][0])


def test_redact_is_a_deep_copy_and_leaves_the_input_alone():
    from app.services.town.snapshot import redact

    full = fake_full()
    before = deep(full)
    out = redact(full)
    assert full == before
    out["shops"][0]["kind"] = "changed"
    out["today"]["invoice_count"] = -1
    assert full == before


def test_strip_names_removes_name_and_code_from_every_shop():
    from app.services.town.snapshot import strip_names

    full = fake_full()
    out = strip_names(full)
    for shop in out["shops"]:
        assert "name" not in shop and "code" not in shop
    text = json.dumps(out)
    for shop in full["shops"]:
        assert shop["name"] not in text and shop["code"] not in text


def test_strip_names_keeps_rank_label_kind_and_counts_but_no_per_shop_amount_or_customer_id():
    from app.services.town.snapshot import strip_names

    full = fake_full()
    before = deep(full)
    out = strip_names(full)
    assert full == before  # input untouched
    for kept, original in zip(out["shops"], full["shops"]):
        for field in ("rank", "account_label", "kind", "today_docs"):
            assert kept[field] == original[field]
        assert not ({"name", "code", "today_amount", "ninety_day_amount"} & set(kept))
    _assert_opaque([s["key"] for s in out["shops"]])
    for shop in full["shops"]:
        assert shop["key"] not in json.dumps(out)
    assert out["today"] == full["today"]  # the banner total stays on a full-variant wallboard


def test_redact_then_strip_names_composes_for_a_wallboard_without_amounts():
    from app.services.town.snapshot import redact, strip_names

    out = strip_names(redact(fake_full()))
    assert not (all_keys(out) & (AMOUNT_KEYS | {"name", "code"}))
    assert [s["kind"] for s in out["shops"]] == ["shop", "shop", "stall"]
    assert not any("rank" in s for s in out["shops"])


def _assert_opaque(keys):
    """An opaque key: "s" + 12 hex characters, unique, no customer id and nothing UUID-shaped."""
    import re

    assert len(set(keys)) == len(keys)
    for key in keys:
        assert re.fullmatch(r"s[0-9a-f]{12}", key), key


def test_opaque_keys_are_stable_for_a_shop_through_the_day():
    """TOWN-V2 sale beat: a poll diffs shop keys. A redacted list is re-sorted by today's documents, so a
    positional key ("s1") moved to another shop when one bought; each shop must keep its key all day, in
    every variant, while the list order changes under it."""
    from app.services.town.snapshot import redact, strip_names

    morning = fake_full()
    later = deep(morning)
    later["shops"][1]["today_docs"] = 9  # the quiet shop buys: it moves to the top of the redacted list
    later["shops"].append({**later["shops"][2], "key": "ZZT-new-stall", "code": "ZZT-S100", "today_docs": 5})
    variants = (redact, strip_names, lambda f: strip_names(redact(f)))
    for variant in variants:
        # identify each output shop by its (kind, account_label, today_docs) in that snapshot
        def keys(full):
            out = variant(full)["shops"]
            return {(s["kind"], s["account_label"], s["today_docs"]): s["key"] for s in out}

        before, after = keys(morning), keys(later)
        assert before[("shop", "A/C II", 3)] == after[("shop", "A/C II", 3)]  # untouched shop: same key
        assert before[("shop", None, 0)] == after[("shop", None, 9)]  # the shop that bought: same key
        assert before[("stall", None, 1)] == after[("stall", None, 1)]  # a new stall does not shift others


def test_opaque_keys_change_from_one_day_to_the_next_and_between_companies():
    from app.services.town.snapshot import opaque_key

    full = fake_full()
    key = full["shops"][0]["key"]
    other_day = {**full, "day": "2026-11-04"}
    other_company = {**full, "company_id": "11111111-1111-1111-1111-111111111111"}
    assert opaque_key(full, key) == opaque_key(deep(full), key)
    assert opaque_key(full, key) != opaque_key(other_day, key)
    assert opaque_key(full, key) != opaque_key(other_company, key)


def test_every_variant_uses_opaque_key_for_each_shop():
    from app.services.town.snapshot import opaque_key, redact, strip_names

    full = fake_full()
    expected = {opaque_key(full, s["key"]) for s in full["shops"]}
    assert {s["key"] for s in redact(full)["shops"]} == expected
    assert {s["key"] for s in strip_names(full)["shops"]} == expected
    assert {s["key"] for s in strip_names(redact(full))["shops"]} == expected  # composing keeps them
