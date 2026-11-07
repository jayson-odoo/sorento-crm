"""Phase 2 RED tests: CHATBOT-TOTALS-FILTERS follow-up (UAC rows WR-1..WR-8,
documentation/plans/chatbot/chatbot-report-widen-reask-acceptance-criteria.md).

Parser outputs are copied as literals from the prod v72 repro (crew/state/handtest/2156/prod-v72-repro, steps 5, 8, 9).
Contract the coder implements: a parse that itself widens (`broaden_to` "all", `entity_op` "clear" or `topic_reset`) does
not carry back a kind whose list the object emptied; a word the held report already settled (held company name, or held
brands) is not asked again as "brand, account type or company?" while `said_as` is null. Every assertion is on the args
that RAN or the question asked.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_report_all_companies_r7 import _sorento_type
from tests.chatbot.test_report_semantic_carry import _ent, _ran, _v, rbot, world  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_totals_filters import SEP, SEPF, _args, _follow, _hold, _kind_slot, _ra2  # noqa: F401
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture

CAT = "ZZT CATEGORY"
THREE_WAY = "brand, account type or company"


def _t1(rbot, sorento: str) -> dict[str, Any]:
    """T1: sales, frame total, delivered, Sep 2026, measure amount, Company Sorento, Brand SORENTO, Category ZZT CATEGORY."""
    ents = (_ent("sorento", "brand", "SORENTO", "company and brand"), _ent(CAT, "category"))
    args = _hold(
        rbot, sorento, group_by=None, entities=ents, flat={"sales_company": sorento},
        brands=["SORENTO"], categories=[CAT],
    )
    assert args.get("brand_ids") and args.get("category_ids") and args.get("company") == DEFAULT_COMPANY_ID, f"setup T1: {args}"
    return args


def _t5(rbot, sorento: str) -> None:
    """T5 state: a channel breakdown held on T1 (brand + category carried by C6-2)."""
    _t1(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    text, calls = rbot.say(
        _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF), "by dealer and project"
    )
    args = _args(calls)
    assert args.get("group_by") == "channel" and args.get("brand_ids") and args.get("category_ids"), f"setup T5: {args} {text!r}"


def _widened(args: dict[str, Any]) -> None:
    assert args.get("group_by") == "channel", args
    assert args.get("company") == DEFAULT_COMPANY_ID, f"company dropped: {args}"
    assert not args.get("brand_ids"), f"brand carried back: {args.get('brand_ids')}"
    assert not args.get("category_ids"), f"category carried back: {args.get('category_ids')}"


def _widen_turn(rbot, sorento: str, message: str, **flat: Any):
    """The object after the message: channel breakdown, company Sorento, brands [] and categories []."""
    ra = _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **flat)
    return rbot.say(v, message)


def test_wr1_all_brand_all_category_widens_both_kinds(rbot, world) -> None:
    """Repro step 8: broaden_axis all, broaden_to all, entity_op clear."""
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "all brand all category", entity_op="clear", broaden_axis="all", broaden_to="all")
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-1: asked {text!r}"
    _widened(_args(calls))


def test_wr2_for_all_brands_and_categories_widens_the_category_too(rbot, world) -> None:
    """Repro step 9: broaden_axis brand, broaden_to all, entity_op reuse."""
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "for all brands and categories", entity_op="reuse", broaden_axis="brand", broaden_to="all")
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-2: asked {text!r}"
    _widened(_args(calls))


@pytest.mark.parametrize("axis", ["all", "brand", "category", "company", None], ids=lambda a: f"axis_{a}")
def test_wr3_all_with_broaden_to_all_on_any_axis_widens_both_kinds(rbot, world, axis) -> None:
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "all", broaden_axis=axis, broaden_to="all")
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-3: asked {text!r}"
    _widened(_args(calls))


@pytest.mark.parametrize("dated", [False, True], ids=["bare_object", "basis_and_period_kept"])
@pytest.mark.parametrize("topic_reset", [True, False], ids=["topic_reset", "no_topic_reset"])
def test_wr4_clear_all_brings_back_no_held_brand_category_or_company(rbot, world, topic_reset, dated) -> None:
    """Repro step 5: every list [], company null, entity_op clear, broaden all/all."""
    sorento, _m = world
    t1 = _t1(rbot, sorento)
    # kind sales, every list empty and company null; `dated` keeps the basis and period the held report had
    ra = _ra2("total", basis="delivered", **SEP) if dated else _ra2("total")
    extra = dict(basis="delivered", **SEPF) if dated else {}
    v = _v("sales_analysis", ra, entity_op="clear", topic_reset=topic_reset, broaden_axis="all", broaden_to="all",
           domain_in_message=True, **extra)
    text, calls = rbot.say(v, "clear all")
    ran = [{k: x for k, x in a.items() if k != "_diagnostics"} for a in _ran(calls)]
    if ran:
        got = ran[-1]
        assert not got.get("brand_ids") and not got.get("category_ids") and not got.get("company"), f"WR-4: {got}"
    else:
        assert text.strip(), "WR-4: neither a report nor a question"
    assert not (ran and ran[-1] == {k: x for k, x in t1.items() if k != "_diagnostics"}), f"WR-4: the T1 total came back: {ran}"


def test_wr5_a_name_the_held_report_settled_is_not_asked_as_brand_account_type_or_company(rbot, world) -> None:
    """Repro step 6 shape: said_as null, SORENTO also a stored account type, held company and brand Sorento."""
    sorento, _m = world
    _sorento_type(rbot)
    _t1(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=sorento, brands=["SORENTO"],
              categories=[CAT], **SEP)
    ent = _ent("sorento", "brand", "SORENTO")
    ent["said_as"] = None
    v = _follow("sales_analysis", ra, ent, group_by="channel", measure="amount", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "sorento total slaes by delaer and proejct")
    assert THREE_WAY not in text.lower() and _kind_slot(rbot).get("asking") != "kind", f"WR-5: asked again: {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "channel" and args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"WR-5: {args}"


# ------------------------------------------------------------------------------------------ locks (green today)


def test_wr6_lock_a_follow_up_that_widens_nothing_carries_the_held_brand_and_category(rbot, world) -> None:
    sorento, _m = world
    t1 = _t1(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="month", measure="amount", company=sorento, **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="month", measure="amount", sales_company=sorento, **SEPF), "by month")
    args = _args(calls)
    assert args.get("group_by") == "month", args
    assert args.get("brand_ids") == t1["brand_ids"] and args.get("category_ids") == t1["category_ids"], f"WR-6: {args}"


def test_wr7_lock_a_bare_name_with_nothing_held_and_said_as_null_asks_the_one_kind_question(rbot, world, monkeypatch) -> None:
    import dataclasses

    from app.services.chatbot.head import parser as parser_mod

    current = parser_mod.resolve_config
    monkeypatch.setattr(parser_mod, "resolve_config", lambda *a, **k: dataclasses.replace(current(*a, **k), said_as=True))
    ent = _ent("sorento", "brand", "SORENTO")
    ent["said_as"] = None
    ra = _ra2(None, basis="delivered", company=None, brands=["SORENTO"], **SEP)
    v = _v("sales_report", ra, ent, basis="delivered", domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "Sorento total sale September 2026")
    assert not _ran(calls) and _kind_slot(rbot).get("asking") == "kind", f"WR-7: {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text


def test_wr8_lock_a_kind_typed_in_the_message_decides(rbot, world) -> None:
    """The message types the kind ("account type"): no question, the typed kind is the filter."""
    sorento, _m = world
    _sorento_type(rbot)
    ra = _ra2(None, basis="delivered", account_types=["SORENTO"], **SEP)
    ent = _ent("sorento", "account_type", "SORENTO", "account type")
    ent["said_as"] = None
    v = _v("sales_report", ra, ent, basis="delivered", domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "sorento account type total sale September 2026")
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-8: asked {text!r}"
    args = _args(calls)
    assert args.get("account_types") == ["SORENTO"] and not args.get("brand_ids"), f"WR-8: {args}"
