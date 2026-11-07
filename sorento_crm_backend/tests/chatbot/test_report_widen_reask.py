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
from tests.chatbot.test_report_totals_filters import SEP, SEPF, _args, _follow, _hold, _kind_slot, _option_position, _ra2, _ra3  # noqa: F401
from tests.chatbot.test_report_totals_filters_ht1 import said_as_on  # noqa: F401 - fixture
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


def _widen_turn(rbot, sorento: str, message: str, ra: dict[str, Any] | None = None, **flat: Any):
    """The object after the message: channel breakdown, company Sorento, brands [] and categories []."""
    ra = ra or _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **flat)
    return rbot.say(v, message)


def _repro_ra() -> dict[str, Any]:
    """The report_ask object of repro steps 8 and 9 as the parser gave it (company Sorento, company_or_brand [SORENTO],
    brands and categories emptied, group_by channel); basis and period are the held report's, filled in so the report runs."""
    ra = _ra3(["SORENTO"], basis="delivered", group_by="channel", company="Sorento", brands=[], categories=[], **SEP)
    ra["frame"] = "breakdown"
    return ra


def test_wr1_all_brand_all_category_widens_both_kinds(rbot, world) -> None:
    """Repro step 8: broaden_axis all, broaden_to all, entity_op clear, the real object."""
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "all brand all category", _repro_ra(), entity_op="clear", broaden_axis="all", broaden_to="all")
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-1: asked {text!r}"
    _widened(_args(calls))


def test_wr2_for_all_brands_and_categories_widens_the_category_too(rbot, world) -> None:
    """Repro step 9: broaden_axis brand, broaden_to all, entity_op reuse, the real object."""
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "for all brands and categories", _repro_ra(), entity_op="reuse", broaden_axis="brand", broaden_to="all")
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-2: asked {text!r}"
    _widened(_args(calls))


@pytest.mark.parametrize("axis", ["all", "brand", "category", None], ids=lambda a: f"axis_{a}")
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


# ------------------------------------------------------------------------------------------ review round 1 (WR-9..WR-14)


def _t1_brand_only(rbot) -> None:
    """Brand SORENTO held with no company: the kind said ("brand"), so the hold runs without a question."""
    ent = _ent("sorento", "brand", "SORENTO", "brand")
    ent["said_as"] = "brand"
    _hold(rbot, None, group_by=None, entities=(ent,), brands=["SORENTO"])


def _bare_sorento_turn(rbot, ra: dict[str, Any], message: str, *, kind_said: Any = None, hint: str = "brand",
                       code: Any = None, raw: str = "sorento", **flat: Any):
    ent = _ent(raw, hint, code, kind_said)
    ent["said_as"] = None
    base = dict(basis="delivered", domain_in_message=True, **SEPF)
    base.update(flat)
    return rbot.say(_v("sales_report", ra, ent, **base), message)


def test_wr9_the_c6_1_company_reading_runs_before_the_settled_name_rule(rbot, world) -> None:
    """C6-1 shape (company Sorento, brands [SORENTO], entity canonical_code null, kind_said null, said_as null) on a held
    T1: company + the held category, no brand."""
    sorento, _m = world
    _sorento_type(rbot)
    _t1(rbot, sorento)
    ra = _ra2(None, basis="delivered", company=sorento, brands=["SORENTO"], **SEP)
    text, calls = _bare_sorento_turn(rbot, ra, "only company sorento", entity_op="modify", continuation=True, sales_company=sorento)
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-9: asked {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"WR-9: {args}"
    assert args.get("category_ids"), f"WR-9: the held category was dropped: {args}"


@pytest.mark.parametrize("flat", [dict(broaden_axis="customer", broaden_to="all"), dict(broaden_axis="date", broaden_to="all")],
                         ids=["axis_customer", "axis_date"])
def test_wr10_a_widen_of_another_axis_keeps_the_held_brand_and_category(rbot, world, flat) -> None:
    sorento, _m = world
    t1 = _t1(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="month", measure="amount", company=sorento, **SEP)
    text, calls = rbot.say(
        _follow("sales_analysis", ra, group_by="month", measure="amount", sales_company=sorento, **SEPF, **flat), "for all customers"
    )
    args = _args(calls)
    assert args.get("brand_ids") == t1["brand_ids"] and args.get("category_ids") == t1["category_ids"], f"WR-10: {args}"


@pytest.mark.usefixtures("said_as_on")
def test_wr11_lock_a_held_brand_only_does_not_settle_the_word_company_brand_both_is_asked(rbot, world) -> None:
    """Brand SORENTO held, no company held; "sorento company only", said_as null: the HT1-5 question. Catches the mutant
    'settled = the held brands only'."""
    _t1_brand_only(rbot)
    ra = _ra2(None, basis="delivered", company=None, brands=["SORENTO"], **SEP)
    text, calls = _bare_sorento_turn(rbot, ra, "sorento company only", continuation=True, entity_op="modify")
    assert _kind_slot(rbot).get("asking") == "kind" and not _ran(calls), f"WR-11: want the one question: {text!r} {_ran(calls)}"


def test_wr12_entity_op_clear_alone_widens_the_lists(rbot, world) -> None:
    """Every broaden field null, entity_op clear, lists emptied ("remove the filters")."""
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "remove the filters", entity_op="clear", broaden_axis=None, broaden_to=None)
    args = _args(calls)
    assert not args.get("brand_ids") and not args.get("category_ids"), f"WR-12: {args}"


def test_wr13_lock_a_typed_kind_beats_the_settled_name_rule_on_a_held_report(rbot, world) -> None:
    """Catches the mutant that drops the `kind_said` check of the settled-name rule."""
    sorento, _m = world
    _sorento_type(rbot)
    _t1(rbot, sorento)
    ra = _ra2(None, basis="delivered", account_types=["SORENTO"], company=sorento, **SEP)
    text, calls = _bare_sorento_turn(rbot, ra, "sorento account type", kind_said="account type", hint="account_type", code="SORENTO",
                                     entity_op="modify", continuation=True, sales_company=sorento)
    assert _kind_slot(rbot).get("asking") != "kind", f"WR-13: asked {text!r}"
    assert _args(calls).get("account_types") == ["SORENTO"], f"WR-13: {_args(calls)}"


def _cob_question_turn(rbot, sorento: str, message: str = "sorento"):
    """The ON-13 / ON-16 shape: object company Sorento + company_or_brand [SORENTO], no widen, kind unsaid."""
    ra = _ra3(["SORENTO"], basis="delivered", company=sorento, **SEP)
    ent = _ent("sorento", "brand", None, None)
    ent["said_as"] = None
    v = _v("sales_report", ra, ent, basis="delivered", domain_in_message=True, sales_company=sorento, continuation=True,
           entity_op="modify", **SEPF)
    return rbot.say(v, message)


@pytest.mark.usefixtures("said_as_on")
def test_wr14_lock_a_topic_reset_carries_nothing_so_the_unsaid_word_is_asked(rbot, world) -> None:
    """The held report holds company AND brand Sorento; topic_reset true; a bare unsaid "sorento": the one question is asked.
    Catches `held_ask=held_ask` passed always (report_ask.py ~:3639)."""
    sorento, _m = world
    _sorento_type(rbot)  # SORENTO is a brand, an account type and a company: only the held report can settle it
    _t1(rbot, sorento)
    ra = _ra2(None, basis="delivered", company=None, brands=["SORENTO"], **SEP)
    text, calls = _bare_sorento_turn(rbot, ra, "sorento total sale September 2026", code="SORENTO", topic_reset=True,
                                     entity_op="replace_combine")
    assert _kind_slot(rbot).get("asking") == "kind" and not _ran(calls), f"WR-14: {text!r} {_ran(calls)}"


@pytest.mark.usefixtures("said_as_on")
def test_wr14_lock_a_held_report_of_another_kind_is_not_carried_into_a_sales_ask(rbot, world) -> None:
    """A held OUTSTANDING report with company AND brand Sorento, then a bare unsaid sales ask: the one question.
    Catches `held_ask=held_ask` passed always."""
    sorento, _m = world
    _sorento_type(rbot)  # SORENTO is a brand, an account type and a company: only the held report can settle it
    ra_o = _ra2(None, kind="outstanding", basis="outstanding", company=sorento, brands=["SORENTO"])
    ent = _ent("sorento", "brand", "SORENTO", "company and brand")
    ent["said_as"] = "both"
    text, calls = rbot.say(_v("outstanding", ra_o, ent, basis="outstanding", domain_in_message=True, sales_company=sorento),
                           "outstanding orders sorento company and brand")
    assert _ran(calls), f"setup: the outstanding report did not run: {text!r}"
    ra = _ra2(None, basis="delivered", company=None, brands=["SORENTO"], **SEP)
    text, calls = _bare_sorento_turn(rbot, ra, "sorento total sale September 2026", code="SORENTO")
    assert _kind_slot(rbot).get("asking") == "kind" and not _ran(calls), f"WR-14: {text!r} {_ran(calls)}"


@pytest.mark.usefixtures("said_as_on")
def test_wr15_lock_no_widen_company_or_brand_word_on_a_held_company_and_brand_is_asked(rbot, world) -> None:
    """No widen, company Sorento + company_or_brand [SORENTO], held company + brand Sorento: the question (ON-13 / ON-16).
    Catches `widens and` removed (~:3444) and `| either` removed (~:3456)."""
    sorento, _m = world
    _t1(rbot, sorento)
    text, calls = _cob_question_turn(rbot, sorento)
    assert _kind_slot(rbot).get("asking") == "kind" and not _ran(calls), f"WR-15: {text!r} {_ran(calls)}"


@pytest.mark.usefixtures("said_as_on")
def test_m6_lock_the_open_question_owes_the_word_so_the_settled_rule_stays_out(rbot, world) -> None:
    """Held company + brand Sorento; the company-or-brand question is open on Sorento; the reply names it again in the
    asked-word slot with no pick: asked again. Catches `key not in owed` removed (~:3456)."""
    sorento, _m = world
    _sorento_type(rbot)  # SORENTO is a brand, an account type and a company: only the held report can settle it
    _t1(rbot, sorento)
    text, calls = _cob_question_turn(rbot, sorento)
    assert _kind_slot(rbot).get("asking") == "kind", f"setup: no open question: {text!r}"
    ra = _ra2(None, basis="delivered", company=sorento, **SEP)
    ra["brand_or_account_type"] = ["SORENTO"]
    ent = _ent("sorento", "brand", None, None)
    ent["said_as"] = None
    v = _v("sales_report", ra, ent, basis="delivered", continuation=True, entity_op="reuse", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "sorento")
    assert _kind_slot(rbot).get("asking") == "kind" and not _ran(calls), f"M6: {text!r} {_ran(calls)}"


@pytest.mark.parametrize("axis", ["date", "customer"], ids=["axis_date", "axis_customer"])
def test_wr12b_entity_op_clear_widens_on_any_axis(rbot, world, axis) -> None:
    """entity_op clear with broaden_to all on a non-product axis, lists emptied, company null: no held brand, category or
    company comes back."""
    sorento, _m = world
    _t5(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=None, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=None, **SEPF,
                entity_op="clear", broaden_axis=axis, broaden_to="all")
    text, calls = rbot.say(v, "clear everything")
    args = _args(calls)
    assert not args.get("brand_ids") and not args.get("category_ids") and not args.get("company"), f"WR-12b: {args}"


def test_wr16_lock_broaden_all_on_the_account_type_axis_widens_the_lists(rbot, world) -> None:
    """Catches "account_type" removed from `_LIST_WIDEN_AXES`."""
    sorento, _m = world
    _t5(rbot, sorento)
    text, calls = _widen_turn(rbot, sorento, "all account types", broaden_axis="account_type", broaden_to="all")
    _widened(_args(calls))


def test_wr17_lock_one_kinds_widen_keeps_the_held_company(rbot, world) -> None:
    """broaden_to all on the brand axis, object company null, held company Sorento: the company is kept, only a clear drops
    it. Catches `cleared = widens` (~:3731)."""
    sorento, _m = world
    _t5(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=None, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=None, **SEPF,
                broaden_axis="brand", broaden_to="all")
    text, calls = rbot.say(v, "all brands")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"WR-17: {args}"


@pytest.mark.parametrize("raw", ["srt", "  SORENTO ", "Sorento"], ids=["abbrev", "case_spacing", "case"])
def test_m9_lock_a_raw_that_differs_in_form_from_the_code_is_still_the_settled_held_brand(rbot, world, raw) -> None:
    """Held as company AND brand (T1); the entity's raw differs in form from its canonical code: still settled, no question."""
    sorento, _m = world
    _sorento_type(rbot)
    _t1(rbot, sorento)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company=sorento, brands=["SORENTO"], **SEP)
    ent = _ent(raw, "brand", "SORENTO", None)
    ent["said_as"] = None
    v = _follow("sales_analysis", ra, ent, group_by="channel", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, f"{raw.strip()} by dealer and project")
    assert _kind_slot(rbot).get("asking") != "kind", f"M9: asked {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"M9: {args}"


def test_m6_unit_an_owed_word_stays_asked_although_the_held_ask_settled_it() -> None:
    """Direct `_word_kinds`: the three-way question is open and owes "sorento" (kind_words), its reply leaves the word in
    brand_or_account_type with no pick, and the held ask holds company Sorento AND brand Sorento. The word stays unsure
    (asked again). Catches `key not in owed` removed from the settled-name rule (report_ask.py ~:3456)."""
    from types import SimpleNamespace

    from app.services.chatbot.lanes.business import report_ask

    focus = SimpleNamespace(required_ask={"ask": report_ask.ASK_NAME, "values": {}, "extras": {"kind_words": ["sorento"]}})
    ask = {"brands": [], "account_types": [], "company_or_brand": [], "brand_or_account_type": ["sorento"], "company": "Sorento"}
    held = {"kind": "sales", "company": "Sorento", "brands": ["Sorento"]}
    out = report_ask._word_kinds(
        ask, {"entities": []}, focus, None, company="Sorento", companies=[("c1", "Sorento", "SOR")], held_ask=held
    )
    assert [(w, how) for w, how, _e, _s in out] == [("sorento", "unsure")], out
