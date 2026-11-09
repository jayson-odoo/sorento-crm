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
    assert [s["key"] for s in out["shops"]] == ["s1", "s2", "s3"]
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
    assert [s["key"] for s in out["shops"]] == ["s1", "s2", "s3"]
    for shop in full["shops"]:
        assert shop["key"] not in json.dumps(out)
    assert out["today"] == full["today"]  # the banner total stays on a full-variant wallboard


def test_redact_then_strip_names_composes_for_a_wallboard_without_amounts():
    from app.services.town.snapshot import redact, strip_names

    out = strip_names(redact(fake_full()))
    assert not (all_keys(out) & (AMOUNT_KEYS | {"name", "code"}))
    assert [s["kind"] for s in out["shops"]] == ["shop", "shop", "stall"]
    assert not any("rank" in s for s in out["shops"])
