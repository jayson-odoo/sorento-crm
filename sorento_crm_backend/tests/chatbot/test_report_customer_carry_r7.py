"""Round 7 RED tests, O-R3 and O-R4 (owner 3 Nov): a held customer is never dropped by a follow-up that names no
customer (both paths); "<customer> only" after a report narrows it (flag on).

Harness reused from the R3 diagnosis: the resolver is made to say the word "zzcust" is a customer AND a supplier on the
first turn (the reconcile kind pick), a customer row "ZZT ZZCUST SDN BHD" is seeded, the model's verdicts are the
v71-shaped ones (flag off) or carry the `report_ask` object (flag on). Every assertion is on the args that RAN.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_report_semantic_carry import (  # noqa: F401 - fixtures
    _FIXTURES, _ent, _flag_on, _pick_of, _ra, _ran, _record_blocks, _v, bot, console, rbot, world,
)
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401

OCT = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
OCTF = {"date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}
WORD = "zzcust"
CUST = "ZZT ZZCUST SDN BHD"
OTHER = "ZZT OTHERCUST SDN BHD"
COMPANY_Q = "{} or {}?"


def _seed(b, name: str = CUST) -> str:
    from tests._mc_lookup_seed import customer

    db = b.console.session_factory()
    try:
        cid = customer(db, company_id=DEFAULT_COMPANY_ID, name=name).id
        db.commit()
        return str(cid)
    finally:
        db.close()


def _kind_pick_on(monkeypatch, state: dict) -> None:
    """On the turn where state['inject'] is set the resolver says WORD is both a customer and a supplier."""
    from app.services.chatbot import turn_runtime

    real = turn_runtime.resolve_kinds

    def _wrap(*a, **k):
        out = real(*a, **k)
        if not state.get("inject"):
            return out
        hits = {"customer": 1, "supplier": 1}
        return dataclasses.replace(
            out, resolved_kinds={**(out.resolved_kinds or {}), WORD: hits}, exact_kinds={**(out.exact_kinds or {}), WORD: hits}
        )

    monkeypatch.setattr(turn_runtime, "resolve_kinds", _wrap)


def _must_run(text: str, calls, tag: str, sorento: str, mocha: str) -> dict[str, Any]:
    ran = _ran(calls)
    assert ran, f"{tag}: the report did not run; the bot said {text.strip()!r}"
    assert COMPANY_Q.format(sorento, mocha) not in text, f"{tag}: O-R2, the company was asked"
    return ran[0]


def _opening(b, sorento: str, mocha: str, state: dict, *, kind_pick: bool, cid: str, flag_on: bool, drops: bool) -> None:
    """T1 "dealer zzcust oct sale" (+ the kind pick) then "invoiced". Asserts the run carries the customer."""
    ra1 = _ra(channel="dealer", customers=[WORD], **OCT)
    t1 = _v("sales_report", ra1, _ent(WORD, "customer"), sales_channel="dealer", domain_in_message=True,
            basis=None, sales_basis=None, **OCTF)
    state["inject"] = kind_pick
    text, calls = b.say(t1, "dealer zzcust oct sale")
    state["inject"] = False
    if kind_pick:
        lines = {ln.split(". ", 1)[1]: int(ln.split(". ", 1)[0]) for ln in text.splitlines() if ln[:1].isdigit() and ". " in ln}
        pos = next((p for label, p in lines.items() if "(customer)" in label), 1)
        pick = _v("sales_report", _ra(channel="dealer", customers=[WORD], **OCT), message_type="answer",
                  intent_hint=None, domain_hint=None, entities=[], reference_positions=[pos],
                  date_filter_start=None, date_filter_end=None, basis=None)
        text, calls = b.say(pick, "customer")
    later = [] if drops else [WORD]
    ra_inv = _ra(channel="dealer", basis="invoiced", customers=later, **OCT)
    text, calls = b.say(_v("sales_ranking", ra_inv, basis="invoiced", entity_op="reuse", continuation=True,
                           open_question_answer=_pick_of(1)), "invoiced")
    args = _must_run(text, calls, "after 'invoiced'", sorento, mocha)
    assert args.get("customer_ids") == [cid], f"O-R3: 'invoiced' lost the customer: {args}"
    assert args.get("channel") == "dealer" and args.get("date_from") == "2026-10-01", args
    assert args.get("basis") == "invoiced" and "company" not in args, args


def _follow_ups(b, sorento: str, mocha: str, cid: str, *, drops: bool) -> None:
    later = [] if drops else [WORD]
    ra_b = _ra(channel="dealer", basis="invoiced", customers=later, group_by="product", **OCT)
    text, calls = b.say(_v("sales_analysis", ra_b, group_by="product", sales_basis="invoiced", entity_op="reuse",
                           continuation=True, report_breakdown=True), "breakdown product")
    args = _must_run(text, calls, "breakdown product", sorento, mocha)
    assert args.get("customer_ids") == [cid] and args.get("group_by") == "product", f"O-R3: breakdown lost the customer: {args}"
    ra_t = _ra(channel="dealer", basis="invoiced", customers=later, group_by="product", top_n=5, measure="qty", **OCT)
    text, calls = b.say(_v("sales_ranking", ra_t, group_by="product", top_n=5, measure="qty", basis="invoiced",
                           rank_direction="top", entity_op="reuse", continuation=True, ranking_refine=True),
                        "top 5, by invoiced qty")
    args = _must_run(text, calls, "top 5 by invoiced qty", sorento, mocha)
    assert args.get("customer_ids") == [cid], f"O-R3: 'top 5, by invoiced qty' lost the customer: {args}"
    assert args.get("top_n") == 5 and args.get("measure") == "qty", args


# ------------------------------------------------------------------------------------------ O-R3 flag off


@pytest.mark.parametrize("kind_pick", [True, False], ids=["kind-pick", "no-pick"])
def test_o_r3_flag_off_the_customer_survives_basis_breakdown_and_top_n(bot, world, monkeypatch, kind_pick) -> None:
    """O-R3 + O-R2 (flag OFF, v71 shapes): zzcust is customer and supplier, the kind pick, the basis, then two refines;
    every run carries the customer's row and no company question is asked. no-pick is the control (customer part)."""
    sorento, mocha = world
    cid = _seed(bot)
    state: dict = {}
    _kind_pick_on(monkeypatch, state)
    _opening(bot, sorento, mocha, state, kind_pick=kind_pick, cid=cid, flag_on=False, drops=False)
    _follow_ups(bot, sorento, mocha, cid, drops=False)


def test_o_r3_flag_off_one_company_contact_kind_pick_keeps_the_customer_row(bot, monkeypatch) -> None:
    """O-R3 isolated from O-R2 (flag OFF, ONE-company staff contact: no company question is possible): zzcust is customer
    and supplier, the kind pick "customer", then "invoiced" -> the run carries the customer's row. Today it is empty (the
    pick entity has no uuid and `answers_the_plan` drops the resolver's row)."""
    cid = _seed(bot)
    state: dict = {}
    _kind_pick_on(monkeypatch, state)
    _opening(bot, "Sorento", "Mocha", state, kind_pick=True, cid=cid, flag_on=False, drops=False)
    _follow_ups(bot, "Sorento", "Mocha", cid, drops=False)


def test_o_r3_flag_on_one_company_contact_kind_pick_keeps_the_customer_row(rbot, monkeypatch) -> None:
    """O-R3 isolated from O-R2 (flag ON, ONE-company staff contact): the object drops customers on every later turn."""
    cid = _seed(rbot)
    state: dict = {}
    _kind_pick_on(monkeypatch, state)
    _opening(rbot, "Sorento", "Mocha", state, kind_pick=True, cid=cid, flag_on=True, drops=True)
    _follow_ups(rbot, "Sorento", "Mocha", cid, drops=True)


def _held_customer(bot, sorento: str, mocha: str, cid: str) -> None:
    ra = _ra(channel="dealer", basis="invoiced", customers=[WORD], **OCT)
    text, calls = bot.say(
        _v("sales_report", ra, _ent(WORD, "customer"), sales_channel="dealer", basis="invoiced", sales_basis="invoiced",
           domain_in_message=True, **OCTF), "dealer zzcust oct sale invoiced")
    args = _must_run(text, calls, "setup", sorento, mocha)
    assert args.get("customer_ids") == [cid], f"setup: {args}"


CARRY_SHAPES = {
    "refine": dict(ranking_refine=True, continuation=True, entity_op="modify"),
    "reuse": dict(continuation=True, entity_op="reuse"),
    "replace_combine_brand": dict(continuation=True, entity_op="replace_combine"),
}


@pytest.mark.parametrize("shape", list(CARRY_SHAPES))
def test_o_r3_flag_off_a_follow_up_naming_no_customer_keeps_the_held_customer(bot, world, shape) -> None:
    """O-R3 (flag OFF): a follow-up with no customer entity in this message, in each carry shape, keeps customer_ids.
    `replace_combine_brand` names another KIND (a brand) and no customer."""
    sorento, mocha = world
    cid = _seed(bot)
    _held_customer(bot, sorento, mocha, cid)
    ents = [_ent("sorento", "brand", "SORENTO")] if shape == "replace_combine_brand" else []
    ra = _ra(channel="dealer", basis="invoiced", group_by="month", **OCT)
    v = _v("sales_analysis", ra, *ents, group_by="month", sales_basis="invoiced", by_words="by month", **CARRY_SHAPES[shape])
    text, calls = bot.say(v, "and by month")
    args = _must_run(text, calls, shape, sorento, mocha)
    assert args.get("customer_ids") == [cid], f"O-R3: a follow-up naming no customer dropped it ({shape}): {args}"


def test_o_r3_control_a_follow_up_naming_another_customer_replaces_the_held_one(bot, world) -> None:
    """Control (flag OFF): a new customer replaces, never combines with, the held one."""
    sorento, mocha = world
    cid = _seed(bot)
    other = _seed(bot, OTHER)
    _held_customer(bot, sorento, mocha, cid)
    ra = _ra(channel="dealer", basis="invoiced", customers=["othercust"], **OCT)
    v = _v("sales_report", ra, _ent("othercust", "customer"), sales_basis="invoiced", basis="invoiced", entity_op="replace_combine",
           continuation=True, domain_in_message=True, **OCTF)
    text, calls = bot.say(v, "how about othercust")
    args = _must_run(text, calls, "replace", sorento, mocha)
    assert args.get("customer_ids") == [other], f"control: want only the other customer, got {args}"


# ------------------------------------------------------------------------------------------ O-R3 flag on


@pytest.mark.parametrize("kind_pick", [True, False], ids=["kind-pick", "no-pick"])
def test_o_r3_flag_on_a_model_that_drops_the_customer_each_turn_keeps_it(rbot, world, monkeypatch, kind_pick) -> None:
    """O-R3 + C6-2 (flag ON): the object's `customers` is [] on 'invoiced', 'breakdown product' and 'top 5' (no entity
    names a customer in those messages): the held customer stays on every run, no company question."""
    sorento, mocha = world
    cid = _seed(rbot)
    state: dict = {}
    _kind_pick_on(monkeypatch, state)
    _opening(rbot, sorento, mocha, state, kind_pick=kind_pick, cid=cid, flag_on=True, drops=True)
    _follow_ups(rbot, sorento, mocha, cid, drops=True)


# ------------------------------------------------------------------------------------------ O-R4 (flag on)


@pytest.mark.parametrize("shape", ["refine", "replace_cont", "reuse_cont"])
@pytest.mark.parametrize("words", ["zzcust only", "customer zzcust only"])
def test_o_r4_a_customer_only_narrows_the_report_to_it(rbot, world, shape, words) -> None:
    """O-R4 (flag ON): after a report, '<customer> only' runs the same report for that customer, no question, no menu."""
    sorento, mocha = world
    cid = _seed(rbot)
    ra0 = _ra(channel="dealer", basis="invoiced", company=sorento, **OCT)
    text, calls = rbot.say(
        _v("sales_report", ra0, sales_channel="dealer", basis="invoiced", sales_basis="invoiced", sales_company=sorento,
           domain_in_message=True, **OCTF), "sorento dealer oct sale invoiced")
    assert _ran(calls), f"setup: {text!r}"
    shapes = {
        "refine": dict(ranking_refine=True, continuation=True, entity_op="modify"),
        "replace_cont": dict(continuation=True, entity_op="replace_combine"),
        "reuse_cont": dict(continuation=True, entity_op="reuse"),
    }
    ra = _ra(channel="dealer", basis="invoiced", company=sorento, customers=[WORD], **OCT)
    ent = _ent(WORD, "customer", None, "customer" if words.startswith("customer") else None)
    text, calls = rbot.say(_v("sales_report", ra, ent, sales_basis=None, basis=None, **shapes[shape]), words)
    ran = _ran(calls)
    assert ran, f"O-R4: no run; the bot said {text.strip()!r}"
    args = ran[0]
    assert args.get("customer_ids") == [cid] and args.get("channel") == "dealer", f"O-R4: {args}"
    assert args.get("basis") == "invoiced" and args.get("date_from") == "2026-10-01" and args.get("company") == DEFAULT_COMPANY_ID, args
    assert "?" not in text.splitlines()[0], f"O-R4: a question or menu came back: {text!r}"


# ------------------------------------------------------------------------------------------ round 7b


@pytest.mark.parametrize(
    "widen",
    [
        dict(broaden_axis="customer", broaden_to="all"),
        dict(ranking_drill="global"),
        dict(self_reference=True),
    ],
    ids=["all-customers", "ranking-drill-global", "my-sales"],
)
def test_b1_flag_on_a_kind_the_parse_itself_widens_is_not_carried(rbot, world, widen) -> None:
    """B1 (flag ON, regression vs 4a5babb25b; C6-2 'a held filter carries ... except a kind the parse widens'): 'how about all
    customers' / a global drill / 'my sales' with the object's customers [] runs with the held customer DROPPED."""
    sorento, mocha = world
    cid = _seed(rbot)
    _held_customer(rbot, sorento, mocha, cid)
    ra = _ra(channel="dealer", basis="invoiced", customers=[], **OCT)
    v = _v("sales_report", ra, basis="invoiced", entity_op="reuse", continuation=True, **widen)
    text, calls = rbot.say(v, "how about all customers")
    ran = _ran(calls)
    assert ran, f"B1: no run; the bot said {text.strip()!r}"
    assert not ran[0].get("customer_ids"), f"B1: the widened ask kept the held customer: {ran[0]}"
    if widen.get("self_reference"):
        assert ran[0].get("mine") is True, f"B1: 'my sales' did not run as mine: {ran[0]}"


def test_s3_flag_off_replace_naming_no_subject_keeps_the_customer_and_the_channel(bot, world) -> None:
    """S3 (owner O-R3 3 Nov supersedes the older 'replace drops the customer' pin for a message that names no subject):
    held customer + dealer channel, 'and by month' with entity_op replace and NO current-message entity keeps both."""
    sorento, mocha = world
    cid = _seed(bot)
    _held_customer(bot, sorento, mocha, cid)
    ra = _ra(channel="dealer", basis="invoiced", group_by="month", **OCT)
    v = _v("sales_analysis", ra, group_by="month", sales_basis="invoiced", by_words="by month", continuation=True,
           entity_op="replace", **OCTF)
    text, calls = bot.say(v, "and by month")
    args = _must_run(text, calls, "replace", sorento, mocha)
    assert args.get("customer_ids") == [cid], f"S3: entity_op replace dropped the held customer: {args}"
    assert args.get("channel") == "dealer" and args.get("group_by") == "month", f"S3: {args}"


def _two_customers_and_a_supplier_word(bot) -> tuple[str, str]:
    c1 = _seed(bot)
    c2 = _seed(bot, "ZZT ZZCUST TRADING")
    return c1, c2


def _first_ask(text_state: dict | None = None):
    ra1 = _ra(channel="dealer", customers=[WORD], **OCT)
    return _v("sales_report", ra1, _ent(WORD, "customer"), sales_channel="dealer", domain_in_message=True,
              basis="invoiced", sales_basis="invoiced", **OCTF)


def test_s1_flag_off_a_kind_pick_with_two_matching_customers_asks_which_one_never_merges(bot, monkeypatch) -> None:
    """S1 (rule A: a picked kind binds its rows, but never merges two different customers silently): one-company contact,
    two customers answer to the word plus a supplier. Kind pick 'customer' -> the SAME which-one question the typed word
    gets with no kind pick, nothing runs; picking one runs that customer only."""
    c1, c2 = _two_customers_and_a_supplier_word(bot)
    state: dict = {}
    _kind_pick_on(monkeypatch, state)
    # the reference path: the word typed as a customer, no kind pick
    text0, calls0 = bot.say(_first_ask(), "dealer zzcust oct sale invoiced")
    assert not _ran(calls0) and text0.strip(), f"setup: want the which-one question for the typed word, got {calls0}"
    # the kind-pick path (a fresh ask replaces the open question)
    state["inject"] = True
    text1, calls1 = bot.say(_first_ask(), "dealer zzcust oct sale invoiced")
    state["inject"] = False
    lines = {ln.split(". ", 1)[1]: int(ln.split(". ", 1)[0]) for ln in text1.splitlines() if ln[:1].isdigit() and ". " in ln}
    pos = next((p for label, p in lines.items() if "(customer)" in label), None)
    assert pos is not None and not _ran(calls1), f"setup: want the kind question, got {text1!r}"
    pick = _v("sales_report", _ra(channel="dealer", customers=[WORD], **OCT), message_type="answer", intent_hint=None,
              domain_hint=None, entities=[], reference_positions=[pos], date_filter_start=None, date_filter_end=None, basis=None)
    text2, calls2 = bot.say(pick, "customer")
    assert not _ran(calls2), f"S1: the kind pick ran the report: {_ran(calls2)}"
    assert text2.strip() == text0.strip(), f"S1: want the typed word's which-one question {text0!r}, got {text2!r}"
    one = _v("sales_report", _ra(channel="dealer", customers=[WORD], **OCT), message_type="answer", intent_hint=None,
             domain_hint=None, entities=[], reference_positions=[1], open_question_answer=_pick_of(1),
             date_filter_start=None, date_filter_end=None, basis=None)
    text3, calls3 = bot.say(one, "the first")
    ran = _ran(calls3)
    assert ran and len(ran[0].get("customer_ids") or []) == 1 and ran[0]["customer_ids"][0] in (c1, c2), (
        f"S1: picking one must run that customer only, got {ran or text3!r}"
    )
