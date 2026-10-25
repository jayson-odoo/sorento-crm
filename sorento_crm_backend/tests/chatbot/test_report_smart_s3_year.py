"""REPORT-SMART-L round S3, AC-S3-3: a product entity equal to the parser's period year is the period.

"Top 5 salesppl in 2026 for cb6635": the parser reads 2026 as the period AND takes the index
candidate '2026' as a product. The entity is dropped at the entity seam, so the ranking runs over
the CB6635 family only. No period set, or another year, keeps the entity; the resolver's substring
tier stays untouched (a partial code still answers its family). Fake codes only.
"""
from __future__ import annotations

import json
from typing import Any

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import _parser_output, stub_access  # noqa: F401
from tests.chatbot.test_report_ask_lane import _e, _rank, console  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_smart_step7 import KEEP, THIS_YEAR, _state_on

FAMILY = ("CB6635-NL", "CB6635-PP")
DECOYS = ("ZZT-B2026-X", "ZZTMGB5020-26", "ZZTB2026-Y")
LAST_YEAR = {"date_filter_start": "2025-01-01", "date_filter_end": "2025-12-31"}


def _seed(console, *codes: str) -> dict[str, str]:
    from tests._mc_lookup_seed import product

    db = console.session_factory()
    try:
        ids = {code: str(product(db, company_id=DEFAULT_COMPANY_ID, code=code).id) for code in codes}
        db.commit()
        return ids
    finally:
        db.close()


def _year_entity(canonical: str | None) -> dict[str, Any]:
    return {**_e("2026", "product"), "canonical_code": canonical}


def _verdict(*entities: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(top_n=5, measure="qty", basis="delivered", state_changes=list(KEEP), **THIS_YEAR)
    base.update(overrides)
    return _rank(*entities, **base)


def _resolver_raws(console) -> list[list[str]]:
    """The entity raws that reached the resolver on each turn."""
    from app.services.chatbot import turn_runtime

    seen: list[list[str]] = []
    real = turn_runtime.resolve_kinds

    def spy(db: Any, *, ctx: Any, **kw: Any) -> Any:
        entities = (((ctx or {}).get("parse") or {}).get("output") or {}).get("entities") or []
        seen.append([str(e.get("raw")) for e in entities if isinstance(e, dict)])
        return real(db, ctx=ctx, **kw)

    console.monkeypatch.setattr(turn_runtime, "resolve_kinds", spy)
    return seen


def test_s3_3_a_product_entity_equal_to_the_period_year_is_dropped_and_the_family_ranks(console) -> None:
    _state_on(console)
    ids = _seed(console, *FAMILY, *DECOYS)
    seen = _resolver_raws(console)
    text, calls = console.say(
        _verdict(_year_entity(DECOYS[0]), _e("cb6635", "product")),
        "Top 5 salesppl in 2026 for cb6635, by delivered qty",
    )
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert args["date_from"] == "2026-01-01" and args["date_to"] == "2026-12-31", args
    assert args["group_by"] == "sales_agent" and args["top_n"] == 5, args
    blob = json.dumps(args) + text
    for decoy in DECOYS:
        assert decoy not in blob and ids[decoy] not in blob, (decoy, args, text)
    if "product_ids" in args:
        assert set(args["product_ids"]) <= {ids[c] for c in FAMILY}, args
    else:
        assert str(args.get("product_code", "")).upper().startswith("CB6635"), args
    assert all("2026" not in raws for raws in seen), seen  # the year never reaches the resolver


def test_s3_3_near_miss_the_year_with_no_period_set_is_kept_as_today(console) -> None:
    _state_on(console)
    _seed(console, *FAMILY, *DECOYS)
    seen = _resolver_raws(console)
    console.say(
        _verdict(_year_entity(None), _e("cb6635", "product"), date_filter_start=None, date_filter_end=None),
        "Top 5 salesppl for 2026 cb6635, by delivered qty",
    )
    assert any("2026" in raws for raws in seen), seen


def test_s3_3_near_miss_the_year_next_to_a_period_in_another_year_is_kept_as_today(console) -> None:
    _state_on(console)
    _seed(console, *FAMILY, *DECOYS)
    seen = _resolver_raws(console)
    console.say(
        _verdict(_year_entity(None), _e("cb6635", "product"), **LAST_YEAR),
        "Top 5 salesppl in 2025 for 2026 cb6635, by delivered qty",
    )
    assert any("2026" in raws for raws in seen), seen


def test_s3_3_a_partial_code_still_answers_its_family_substring_tier_untouched(console) -> None:
    _state_on(console)
    ids = _seed(console, "MWC7601-RL-S12", "IBWC7601-RL-S10", "ZZT-OTHER-1")
    text, calls = console.say(_verdict(_e("WC7601", "product")), "Top 5 salesppl in 2026 for WC7601, by delivered qty")
    assert len(calls) == 1, (text, calls)
    args = calls[0]
    assert "product_code" in args or "product_ids" in args, args
    if "product_ids" in args:
        assert set(args["product_ids"]) == {ids["MWC7601-RL-S12"], ids["IBWC7601-RL-S10"]}, args
    else:
        assert "WC7601" in str(args["product_code"]).upper(), args
    assert "ZZT-OTHER-1" not in json.dumps(args), args
