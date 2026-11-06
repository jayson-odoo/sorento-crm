"""REPORT-FILTER-ALL: the parser's `report_ask` object is final; every filter slot has an explicit ALL.

Plan `documentation/plans/chatbot/PLAN-report-filter-all-5nov.md`, UAC `report-filter-all-acceptance-criteria.md`.
Contract (nothing else is assumed):
* A prompt that writes `parser.REPORT_ALL_WORD` (`["ALL"]`) defines ALL: `report_ask_defined` holds "ALL", and the
  schema's channel enum offers "ALL".
* With ALL defined, a filter slot written ALL (company / channel "ALL", a list holding "ALL") is no filter, in the
  report and in the held state after it. An empty slot over a held value, without ALL, keeps the held value (the ONE
  safety rule, `report_ask._keep_held`), whatever the legacy `broaden_axis` / `scope_intent` / `entity_op` say.
* A company name that is none of the contact's own but a near spelling of the held one is the held one.
* Without ALL defined (a prompt before this lane), the legacy broaden-to-all signal reads as ALL (`_legacy_all`; the
  CL rows of test_report_totals_filters lock it).

The follow-up objects replay the owner's #2156 phrasings ("clear brand", "all customers", "any agent", "clear all",
"remove one of two brands", "break down project and retail") as the parse the ALL prompt writes for them: the recorded
v202 objects with the cleared slot written ALL and, where the recording left the other held slots out, left out here too
(the forgot-to-echo case). Real engine, report lane and MCP presenter; only the parser verdict and the MCP transport are
doubles. Invented data only.
"""
from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes.business import report_ask
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture
from tests.chatbot.test_report_ask_lane import console_no_grant  # noqa: F401 - fixture
from tests.chatbot.test_report_semantic_carry import _ent, _pick_of, _ran, _v, rbot, world  # noqa: F401 - fixtures + helpers
from tests.chatbot.test_report_totals_filters import (  # noqa: F401 - fixtures + helpers
    _HELD_WORDS,
    _KINDS,
    SEP,
    SEPF,
    _args,
    _asked,
    _follow,
    _frame,
    _hold,
    _ra2,
    _widen,
)
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures
from tests.chatbot.test_report_totals_filters_ht1 import _hold_agents, _t4, said_as_on  # noqa: F401 - fixture + helpers

ALL = parser_mod.REPORT_ALL
FORBIDDEN = "You do not have access to that company."


@pytest.fixture
def all_on(rbot, monkeypatch) -> None:
    """Over `rbot`'s config: the prompt in use defines ALL (`report_ask_defined` holds it), as the ALL prompt does."""
    current = parser_mod.resolve_config

    def _cfg(*a, **k):
        cfg = current(*a, **k)
        return dataclasses.replace(cfg, report_ask_defined=frozenset(cfg.report_ask_defined) | {ALL})

    monkeypatch.setattr(parser_mod, "resolve_config", _cfg)


def _all_of(slot: str) -> Any:
    return ALL if slot in ("company", "channel") else [ALL]


def _hold_all_kinds(rbot, sorento: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Every filter kind held on a delivered September month breakdown (the CL-5 world). Returns (args, held frame)."""
    held_ents = tuple(f() for _k, (_s, f, _a, _b, _c) in _KINDS.items() if f is not None)
    first = _hold(rbot, sorento, group_by="month", entities=held_ents, **_HELD_WORDS)
    return first, dict(_frame(rbot))


# ------------------------------------------------------------------------------------------ FA-1 ALL clears one slot

_PHRASE = {
    "brand": "clear brand", "customer": "all customers", "product": "any product", "category": "all categories",
    "agent": "any agent", "account_type": "all account types", "channel": "all channels", "company": "clear company",
}


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("kind", list(_KINDS))
def test_fa1_all_clears_only_that_slot_and_the_slots_the_object_left_out_stay(rbot, world, kind) -> None:
    """The object writes ALL for one slot and leaves EVERY other filter slot empty (it forgot to echo them), with no
    legacy broaden field: only that filter goes; the rest stay as held, in the report and in the held state."""
    sorento, _m = world
    slot, _ent_of, _axis, arg, frame_key = _KINDS[kind]
    first, held_frame = _hold_all_kinds(rbot, sorento)
    assert first.get(arg) not in (None, [], ""), f"setup: the held report has no {kind} ({arg}): {first}"
    ra = _ra2(None, basis="delivered", group_by="month", measure="amount", **{slot: _all_of(slot)}, **SEP)
    flat = dict(group_by="month", measure="amount", sales_company=None, entity_op="clear", **SEPF)
    text, calls = rbot.say(_follow("sales_analysis", ra, **flat), _PHRASE[kind])
    assert not _asked(text), f"FA-1 {kind}: asked {text!r}"
    args = _args(calls)
    assert not args.get(arg), f"FA-1 {kind}: the filter survived: {arg}={args.get(arg)}"
    frame = _frame(rbot)
    assert not frame.get(frame_key), f"FA-1 {kind}: the held state keeps it: {frame_key}={frame.get(frame_key)}"
    for other, (_s, _f, _a, other_arg, other_key) in _KINDS.items():
        if other == kind:
            continue
        assert args.get(other_arg) == first.get(other_arg), f"FA-1 {kind}: also lost {other}: {args.get(other_arg)!r}"
        assert frame.get(other_key) == held_frame.get(other_key), f"FA-1 {kind}: held state lost {other}"
    assert args.get("basis") == "delivered" and args.get("group_by") == "month", args
    assert args.get("date_from") == "2026-09-01" and args.get("date_to") == "2026-09-30", args


# ------------------------------------------------------------------------------------------ FA-2 the legacy signal is retired


@pytest.mark.usefixtures("all_on")
def test_fa2_with_all_defined_an_empty_slot_beside_the_legacy_widen_signal_keeps_the_held_value(rbot, world) -> None:
    """The legacy `broaden_axis` brand + `broaden_to` all + `scope_intent` broaden are not read for reports once the prompt
    writes ALL: brands [] is a forgotten echo, the held brand stays."""
    sorento, _m = world
    first = _hold(rbot, sorento, group_by="channel", brands=["Sorento"], entities=(_ent("sorento", "brand", "SORENTO", "brand"),))
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **_widen("brand"))
    text, calls = rbot.say(v, "show again")
    assert _args(calls).get("brand_ids") == first["brand_ids"], f"FA-2: {_args(calls)}"


def test_fa2b_without_all_defined_the_legacy_widen_signal_still_clears(rbot, world) -> None:
    """The temporary adapter (`_legacy_all`): the prompt in production before the publish keeps clearing by the old signal."""
    sorento, _m = world
    _hold(rbot, sorento, group_by="channel", brands=["Sorento"], entities=(_ent("sorento", "brand", "SORENTO", "brand"),))
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **_widen("brand"))
    text, calls = rbot.say(v, "all brands")
    assert not _args(calls).get("brand_ids"), f"FA-2b: {_args(calls)}"


# ------------------------------------------------------------------------------------------ FA-3 clear all


@pytest.mark.usefixtures("all_on")
def test_fa3_clear_all_drops_every_filter_and_keeps_basis_period_and_breakdown(rbot, world) -> None:
    """Owner 5 Nov (AGENT-REPORTS Q4, crew Q4): "clear all" is every filter slot ALL, company and channel included; the
    basis, the period and the breakdown stay."""
    sorento, _m = world
    _hold_all_kinds(rbot, sorento)
    every = {slot: _all_of(slot) for slot, *_rest in _KINDS.values()}
    ra = _ra2(None, basis="delivered", group_by="month", measure="amount", **every, **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="month", **SEPF), "clear all")
    assert not _asked(text), f"FA-3: asked {text!r}"
    args = _args(calls)
    for _kind, (_s, _f, _a, arg, _k) in _KINDS.items():
        assert not args.get(arg), f"FA-3: {arg} survived: {args.get(arg)}"
    assert args.get("basis") == "delivered" and args.get("group_by") == "month", args
    assert args.get("date_from") == "2026-09-01" and args.get("date_to") == "2026-09-30", args


# ------------------------------------------------------------------------------------------ FA-4 one of two, mixed ALL, no-op


@pytest.mark.usefixtures("all_on")
def test_fa4_remove_one_of_two_brands_keeps_the_other(rbot, world) -> None:
    sorento, _m = world
    ents = (_ent("sorento", "brand", "SORENTO", "brand"), _ent("cabana", "brand", "CABANA", "brand"))
    first = _hold(rbot, sorento, group_by="channel", brands=["Sorento", "Cabana"], entities=ents)
    assert len(first.get("brand_ids") or []) >= 2, f"setup: {first}"
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, brands=["Cabana"], **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="channel", sales_company=sorento, **SEPF), "remove sorento brand")
    args = _args(calls)
    kept = set(args.get("brand_ids") or [])
    assert kept and kept < set(first["brand_ids"]), f"FA-4: {args}"
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("group_by") == "channel", args


@pytest.mark.usefixtures("all_on")
def test_fa4b_all_beside_a_name_is_the_whole_list(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by="channel", brands=["Sorento"], entities=(_ent("sorento", "brand", "SORENTO", "brand"),))
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, brands=[ALL, "Sorento"], **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="channel", sales_company=sorento, **SEPF), "all brands")
    assert not _args(calls).get("brand_ids"), f"FA-4b: {_args(calls)}"


@pytest.mark.usefixtures("all_on")
def test_fa4c_all_brands_with_no_brand_held_is_a_no_op(rbot, world) -> None:
    sorento, _m = world
    first = _hold(rbot, sorento, group_by="channel")
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, brands=[ALL], **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="channel", sales_company=sorento, **SEPF), "all brands")
    assert not _asked(text), f"FA-4c: asked {text!r}"
    assert _args(calls) == first, f"FA-4c: the report changed:\n{_args(calls)}\nvs\n{first}"


# ------------------------------------------------------------------------------------------ FA-5 the company slot


@pytest.mark.usefixtures("all_on")
def test_fa5_all_companies_runs_with_no_company_filter_and_asks_nothing(rbot, world) -> None:
    sorento, _m = world
    first = _hold(rbot, sorento, group_by="channel")
    assert first.get("company") == DEFAULT_COMPANY_ID, f"setup: {first}"
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=ALL, **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="channel", sales_company=None, **SEPF), "all companies")
    assert not _asked(text) and FORBIDDEN not in text, f"FA-5: {text!r}"
    assert not _args(calls).get("company"), f"FA-5: {_args(calls)}"
    assert not _frame(rbot).get("company"), _frame(rbot)


@pytest.mark.usefixtures("all_on")
def test_fa5b_a_null_company_over_a_held_one_keeps_it(rbot, world) -> None:
    """The forgotten echo: "break down project and retail" with company null over a held Sorento total stays Sorento."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company=None, **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="channel", **SEPF), "break down project and retail")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("group_by") == "channel", f"FA-5b: {args}"


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("sales_company", [None, "Sorento"], ids=["flat-null", "flat-held"])
def test_fa5c_a_misspelled_echo_of_the_held_company_is_the_held_company(rbot, world, sales_company) -> None:
    """HT1-18 (v202 parse "Sorenth" over a held Sorento), now without leaning on the top-level `sales_company`: with it null
    the old rule refused the turn ("no access")."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company="Sorenth", **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", sales_company=sales_company, **SEPF)
    text, calls = rbot.say(v, "break down project and retail")
    assert FORBIDDEN not in text, f"FA-5c: {text!r}"
    assert _args(calls).get("company") == DEFAULT_COMPANY_ID, f"FA-5c: {_args(calls)}"


@pytest.mark.usefixtures("all_on")
def test_fa5d_another_own_company_named_with_no_entity_switches(rbot, world) -> None:
    """HT1-18b under ALL: an exact own company is never read as an echo."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company="Mocha", **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="channel", sales_company="Sorento", **SEPF), "mocha by channel")
    assert _args(calls).get("company") == MOCHA_ID, f"FA-5d: {_args(calls)}"


# ------------------------------------------------------------------------------------------ FA-6 the channel slot


@pytest.mark.usefixtures("all_on")
def test_fa6_all_channels_drops_the_held_channel_and_a_null_one_keeps_it(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by="month", channel="dealer", flat={"sales_channel": "dealer"})
    ra = _ra2(None, basis="delivered", group_by="month", measure="amount", company=sorento, channel=None, **SEP)
    _t, calls = rbot.say(_follow("sales_analysis", ra, group_by="month", sales_company=sorento, **SEPF), "by month again")
    assert _args(calls).get("channel") == "dealer", f"FA-6 keep: {_args(calls)}"
    ra = _ra2(None, basis="delivered", group_by="month", measure="amount", company=sorento, channel=ALL, **SEP)
    _t, calls = rbot.say(_follow("sales_analysis", ra, group_by="month", sales_company=sorento, **SEPF), "all channels")
    assert not _args(calls).get("channel"), f"FA-6 clear: {_args(calls)}"


# ------------------------------------------------------------------------------------------ review round 1 (engine replays)


@pytest.mark.usefixtures("all_on", "said_as_on")
def test_r1_brand_only_over_a_held_company_of_that_name_keeps_the_company(rbot, world) -> None:
    """Review B1: held Sorento company, every agent; "sorento brand only" with company null (the forgotten echo)."""
    sorento, _m = world
    _hold_agents(rbot, sorento)
    text, calls = rbot.say(_t4("brand", company=None), "sorento brand only")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"R1: {args}"


@pytest.mark.usefixtures("all_on")
def test_r2_a_company_the_message_types_and_the_contact_does_not_hold_is_refused_never_the_held_one(rbot, world) -> None:
    """Review B2: "Sorento SG" is close to the held Sorento, but the user typed it: refused, never Sorento's figures."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company="Sorento SG", **SEP)
    v = _follow("sales_analysis", ra, _ent("Sorento SG", "brand", None, None), group_by="channel", sales_company="Sorento", **SEPF)
    text, calls = rbot.say(v, "Sorento SG sales only")
    assert text.strip() == FORBIDDEN, f"R2: {text!r}"
    assert not _ran(calls), _ran(calls)


@pytest.mark.usefixtures("all_on", "said_as_on")
def test_r3_company_only_over_a_held_company_and_same_name_brand_drops_the_brand(rbot, world) -> None:
    """Review should-fix 5: held company Sorento + brand SORENTO; "sorento company only" (said_as company)."""
    sorento, _m = world
    first = _hold(rbot, sorento, group_by="sales_agent", brands=["Sorento"], entities=(_ent("sorento", "brand", "SORENTO", "brand"),))
    assert first.get("brand_ids"), f"setup: {first}"
    text, calls = rbot.say(_t4("company", company=sorento), "sorento company only")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"R3: {args}"


# ------------------------------------------------------------------------------------------ units


def test_u1_the_prompt_defines_all_by_its_word_and_the_channel_enum_offers_it_only_then() -> None:
    assert ALL not in parser_mod.report_ask_defined_in(parser_mod.REPORT_ASK_LINE)
    text = parser_mod.REPORT_ASK_LINE + '\n"company": "ALL", "brands": ["ALL"]'
    assert ALL in parser_mod.report_ask_defined_in(text)
    base = parser_mod.PARSE_OUTPUT_JSON_SCHEMA
    off = parser_mod.with_report_ask(base, ())["properties"]["report_ask"]["properties"]
    on = parser_mod.with_report_ask(base, {ALL})["properties"]["report_ask"]["properties"]
    assert ALL not in off["channel"]["enum"] and ALL in on["channel"]["enum"]
    assert ALL not in on, "ALL is a value, never a key of the object"


def test_u2_read_all_empties_each_slot_written_all() -> None:
    ask = {"company": ALL, "channel": "dealer", "brands": ["x", "All"], "sales_agents": ["a"], "customers": []}
    assert report_ask._read_all(ask) == {"company", "brands"}, "ALL in any case"
    assert ask["company"] is None and ask["brands"] == [] and ask["channel"] == "dealer" and ask["sales_agents"] == ["a"]


def test_u3_keep_held_refills_only_a_forgotten_slot() -> None:
    held = {"company": "Sorento", "channel": "dealer", "brands": ["Cabana"], "sales_agents": ["A"], "categories": ["T"]}
    ask = {"company": None, "channel": None, "brands": [], "sales_agents": ["B"], "categories": []}
    report_ask._keep_held(ask, held, {"categories"}, None)
    assert ask == {"company": "Sorento", "channel": "dealer", "brands": ["Cabana"], "sales_agents": ["B"], "categories": []}


def test_u4_keep_held_never_refills_the_axis_slot_or_a_name_the_object_moved() -> None:
    held = {"brands": ["Cabana"], "sales_agents": ["A"]}
    ask = {"brands": [], "account_types": ["cabana"], "sales_agents": []}
    report_ask._keep_held(ask, held, set(), "sales_agents")
    assert ask["brands"] == [] and ask["sales_agents"] == [], ask
    held = {"brands": ["Sorento"], "company": None}
    ask = {"brands": [], "company": "Sorento"}
    report_ask._keep_held(ask, held, set(), None)
    assert ask["brands"] == [], f"a name the message calls the company is not refilled as a brand: {ask}"


def test_u4b_a_move_never_un_holds_the_company_and_only_brand_and_account_type_names_move() -> None:
    """Review B1 / M14: "<name> brand only" over a held company of that name keeps the company. Review should-fix 4: a new
    customer "Tan" does not stop a held sales agent "Tan" from refilling (only the real move pairs, `_MOVES`)."""
    held = {"company": "Sorento", "brands": []}
    ask = {"company": None, "brands": ["Sorento"]}
    report_ask._keep_held(ask, held, set(), None)
    assert ask["company"] == "Sorento", ask
    held = {"account_types": ["Cabana"], "brands": []}
    ask = {"account_types": [], "brands": ["Cabana"]}
    report_ask._keep_held(ask, held, set(), None)
    assert ask["account_types"] == [], f"an account type the answer moved to brands is not refilled (review N2): {ask}"
    held = {"sales_agents": ["Tan"], "customers": []}
    ask = {"sales_agents": [], "customers": ["Tan"]}
    report_ask._keep_held(ask, held, set(), None)
    assert ask["sales_agents"] == ["Tan"], ask


@pytest.mark.parametrize(
    "said, held, companies, want",
    [
        ("Sorenth", "Sorento", (), "Sorento"),
        ("Sorenth", "Sorento", (("1", "Sorento", "SOR"), ("2", "Mocha", "MOC")), "Sorento"),
        ("Mocha", "Sorento", (("1", "Sorento", "SOR"), ("2", "Mocha", "MOC")), "Mocha"),
        ("Fujiwara", "Sorento", (("1", "Sorento", "SOR"),), "Fujiwara"),
        ("Sorenth", None, (), "Sorenth"),
        (None, "Sorento", (), None),
        ("SOR", "Sorento", (("1", "Sorento", "SOR"),), "SOR"),
        # Review M10: an own company spelled close to the held one is still that own company.
        ("Sorento SG", "Sorento", (("1", "Sorento", "SOR"), ("3", "Sorento SG", "SSG")), "Sorento SG"),
    ],
)
def test_u5_held_spelling(said, held, companies, want) -> None:
    assert report_ask._held_spelling(said, held, companies) == want


def test_u5b_a_company_this_message_typed_is_never_read_as_an_echo() -> None:
    """Review B2: "Sorento SG" typed by the user (an entity of this message) stays as written, refused downstream."""
    assert report_ask._held_spelling("Sorento SG", "Sorento", (), ["Sorento SG"]) == "Sorento SG"
    assert report_ask._held_spelling("Sorento SG", "Sorento", (), []) == "Sorento"
    assert report_ask._held_spelling("SORENTOG", "Sorento", (), ["sorento g", "SORENTOG"]) == "SORENTOG", "a typed code counts (N3)"
    assert report_ask._held_spelling("SORENTOG", "Sorento", (), ["sorento g"]) == "Sorento", "control: the code is what saved it"


# ------------------------------------------------------------------------------------------ the prompt candidate + gold

_PLANS = __import__("pathlib").Path(__file__).resolve().parents[3] / "documentation" / "plans" / "chatbot"
BASE_MD5 = "d29c19830b22aa47403a88ddcb8e817d"  # production v72 (crew, 5 Nov)
CANDIDATE_MD5 = "289da7e56130a489ecb624031996acc2"


def _md5(path) -> str:
    import hashlib

    return hashlib.md5(path.read_bytes()).hexdigest()


def test_p1_the_candidate_is_the_pinned_v72_base_plus_the_all_edits_and_turns_all_on() -> None:
    base, cand = _PLANS / "prompt-prod-v72-d29c1983.txt", _PLANS / "prompt-report-filter-all.txt"
    assert _md5(base) == BASE_MD5 and _md5(cand) == CANDIDATE_MD5
    text = cand.read_text(encoding="utf-8")
    assert parser_mod.REPORT_ASK_LINE in text and ALL in parser_mod.report_ask_defined_in(text)
    assert ALL not in parser_mod.report_ask_defined_in(base.read_text(encoding="utf-8")), "v72 must stay on the adapter"
    assert {"frame", "company_or_brand"} <= parser_mod.report_ask_defined_in(text), "the v72 keys stay defined"


def test_p2_the_committed_filter_all_gold_file_loads_whole() -> None:
    from pathlib import Path

    from scripts.chatbot_eval import parser_gold as pg

    path = Path(pg.__file__).parent / "gold" / "parser_report_filter_all.jsonl"
    with open(path, encoding="utf-8") as fh:
        want = sum(1 for ln in fh if ln.strip())
    assert want >= 10 and len(pg.load_gold(path)) == want


# ------------------------------------------------------------------------------------------ K: no keyword rule on the path


@pytest.mark.parametrize("text", ["all brands", "clear the brand", "no brand", "sorento"])
def test_k1_an_open_outstanding_list_never_reads_the_words_of_a_report_object_turn(text, monkeypatch) -> None:
    """Owner 5 Nov: no keyword or regex decides a report's filters; the parser's object does. `order_list.clears_the_brand`
    and `brand_word_alone` stand down when the parse carries a report object."""
    from app.services.chatbot import order_list
    from app.services.chatbot.order_list import order_list_verdict
    from app.services.chatbot.turn.state import Focus, State

    # Review N8: with no database `brand_word_alone` never matches; make every word a live brand word so the bare-word
    # switch is really exercised.
    monkeypatch.setattr(order_list, "brand_word_alone", lambda _db, t: t)
    focus = Focus(domains=["order"], status="do_outstanding", outstanding_brand_ids=["b1"])
    verdict = {"order_status": "do_outstanding", "report_ask": _ra2(None, kind="outstanding", brands=[ALL]), "entities": []}
    out, state, rule = order_list_verdict(None, verdict, State(focus=focus), text)
    assert rule is None and out is verdict and state.focus.outstanding_brand_ids == ["b1"], rule


def test_k1_lock_a_plain_order_list_turn_keeps_its_own_clear() -> None:
    """The order list (no report object) is another lane's: its clear is untouched here."""
    from app.services.chatbot.order_list import order_list_verdict
    from app.services.chatbot.turn.state import Focus, State

    focus = Focus(domains=["order"], status="do_outstanding", outstanding_brand_ids=["b1"])
    _out, state, rule = order_list_verdict(None, {"report_ask": None, "entities": []}, State(focus=focus), "all brands")
    assert rule == "order_list_brand_cleared" and state.focus.outstanding_brand_ids == []


def test_k2_the_report_lane_reads_no_message_text() -> None:
    """No regex and no text read in the report lane: `take_words` takes the text for its seam's shape only."""
    import inspect

    src = inspect.getsource(report_ask)
    assert "import re\n" not in src and "re.compile" not in src and "re.search" not in src


# ------------------------------------------------------------------------------------------ crew gate 5 Nov (round 3)


def _clear_all_object(**over: Any) -> dict[str, Any]:
    """The T5 / X parse of "clear all" on the ALL prompt: every filter slot ALL, the report's own slots left null (the
    parser did not echo the period, basis, frame or axis)."""
    every = {slot: _all_of(slot) for slot, *_rest in _KINDS.values()}
    ra = _ra2(None, basis=None, group_by=None, measure=None, **every, date_from=None, date_to=None)
    ra.update(over)
    return ra


@pytest.mark.usefixtures("all_on")
def test_g1_clear_all_with_the_report_slots_left_null_keeps_period_basis_and_breakdown(rbot, world) -> None:
    """Crew gate T5 / X "clear all": the period and the basis were lost and asked again. The one keep rule covers every
    slot of the held report: null keeps, a value replaces, ALL clears."""
    sorento, _m = world
    _hold_all_kinds(rbot, sorento)
    v = _follow("sales_analysis", _clear_all_object(), basis=None, group_by=None)
    text, calls = rbot.say(v, "clear all")
    assert not _asked(text), f"G1: asked {text!r}"
    args = _args(calls)
    for _kind, (_s, _f, _a, arg, _k) in _KINDS.items():
        assert not args.get(arg), f"G1: {arg} survived: {args.get(arg)}"
    assert args.get("basis") == "delivered" and args.get("group_by") == "month", args
    assert args.get("date_from") == "2026-09-01" and args.get("date_to") == "2026-09-30", args


@pytest.mark.usefixtures("all_on")
def test_g1b_an_explicit_total_still_drops_the_held_axis(rbot, world) -> None:
    """The rule keeps only what the object left null: an explicit total frame is the parser's call (AF-3)."""
    sorento, _m = world
    _hold_all_kinds(rbot, sorento)
    v = _follow("sales_report", _clear_all_object(frame="total"), basis=None, group_by=None)
    text, calls = rbot.say(v, "total only, no filter")
    args = _args(calls)
    assert not args.get("group_by") and args.get("basis") == "delivered" and args.get("date_from") == "2026-09-01", args


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("message_type", ["casual", None])
def test_g3_a_report_object_over_a_held_report_runs_the_report_even_when_the_rest_of_the_parse_reads_chit_chat(
    rbot, world, message_type
) -> None:
    """Crew gate X "清除所有筛选": the object was all ALL but the turn answered as chit-chat. The object is the parser's
    own statement that this is a report ask (it is null on every other message): the report runs."""
    sorento, _m = world
    _hold_all_kinds(rbot, sorento)
    v = _v(
        None, _clear_all_object(), order_status=None, domain_hint=None, intent_hint=None, message_type=message_type,
        basis=None, group_by=None, entity_op=None, continuation=None, domain_in_message=False,
    )
    text, calls = rbot.say(v, "清除所有筛选")
    args = _args(calls)
    assert args.get("basis") == "delivered" and args.get("date_from") == "2026-09-01", args
    assert not args.get("brand_ids") and not args.get("company"), args


def test_g5_a_report_object_turn_never_reads_its_names_as_a_supplier() -> None:
    """Crew gate steps 8 / 12: "Sorento company, brands Sorento and Cabana" answered "Sorry, I couldn't find a supplier
    called Sorento" (the span list placed Sorento on supplier rows). A kept report object names no supplier."""
    from types import SimpleNamespace

    from app.services.chatbot import engine

    prep = SimpleNamespace(supplier_typed=["Sorento"])
    state = SimpleNamespace(pending=None, focus=SimpleNamespace(extra={}))
    supplier = {"raw": "Sorento", "hint": "supplier", "canonical_code": None, "current_message": True}
    report = {"report_ask": _ra2(None, company="Sorento", brands=["Sorento", "Cabana"]), "entities": [supplier]}
    assert engine._supplier_scope(state, state, report, ["order"], True, prep) is None
    plain = {"report_ask": None, "entities": [supplier]}
    assert "supplier" in (engine._supplier_scope(state, state, plain, ["order"], True, prep) or {}).get("line", ""), "lock"


# ------------------------------------------------------------------------------------------ crew gate 6 Nov (round 4)


def _sorento_debtor_type(rbot) -> None:
    """The 1104 copy (a production snapshot) holds a SORENTO debtor type (`autocount_debtor_type`, AutoCount data)."""
    from tests.chatbot.test_sales_account_type_lane import _ledger

    db = rbot.console.session_factory()
    try:
        _ledger(db, DEFAULT_COMPANY_ID, "ZZT SORENTO TYPE LEDGER [A/C IV]", "SORENTO")
        db.commit()
    finally:
        db.close()


def _said(raw: str, said_as: str, typed: str) -> dict[str, Any]:
    ent = _ent(raw, "brand", raw.upper(), None)
    ent.update(said_as=said_as, said_as_text=typed)
    return ent


@pytest.mark.usefixtures("all_on", "said_as_on")
@pytest.mark.parametrize("held_company", [True, False], ids=["company-held", "after-clear-all"])
@pytest.mark.parametrize("order", ["company-first", "brand-first"])
def test_h8_a_name_said_once_as_company_and_once_as_brand_is_both(rbot, world, order, held_company) -> None:
    """Crew gate step 8 "Sorento company, brands Sorento and Cabana" kept CABANA only; step 14 "Sorento company, Sorento
    brand" kept the brand only. The parser's two entities for the word say company and brand: both (owner rule)."""
    sorento, _m = world
    _hold(rbot, sorento if held_company else None, group_by="channel")  # step 14 follows a clear-all: no company held
    ents = [_said("Sorento", "company", "company"), _said("Sorento", "brand", "brands")]
    if order == "brand-first":
        ents.reverse()
    ra = _ra2(None, basis="delivered", group_by="channel", company=sorento, brands=["Sorento", "Cabana"], **SEP)
    v = _follow("sales_analysis", ra, *ents, _ent("Cabana", "brand", "CABANA", "brands"), group_by="channel",
                sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "Sorento company, brands Sorento and Cabana")
    assert _ran(calls), f"H8: nothing ran: {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID, f"H8 company: {args}"
    assert len(args.get("brand_ids") or []) >= 2, f"H8 both brands (SORENTO + CABANA): {args}"


@pytest.mark.usefixtures("all_on", "said_as_on")
def test_h15_a_company_name_that_is_also_a_debtor_type_asks_company_or_brand_once_and_brand_is_every_company(
    rbot, world
) -> None:
    """Crew gate R2 / steps 15-16 (1104): "Sorento total sale delivered September 2026" asked "brand, account type or
    company?" (the SORENTO debtor type), and the brand answer still showed Company Sorento. A name that is one of the
    contact's own companies and a brand is asked company or brand once (owner rule); the brand answer is the brand
    across every company."""
    from tests.chatbot.test_report_totals_filters import _cob_turn, _kind_slot, _option_position, _ra3

    _sorento_debtor_type(rbot)
    text, calls = _cob_turn(rbot, _ra3(["Sorento"], basis="delivered", **SEP))
    assert not _ran(calls), _ran(calls)
    slot = _kind_slot(rbot)
    assert slot.get("asking") == "kind" and "account type" not in text.lower(), f"H15: {text!r}"
    assert "company" in text.lower() and "brand" in text.lower(), text
    pos = _option_position(slot, "brand")
    ra = _ra3([], basis="delivered", brands=["SORENTO"], **SEP)
    v = _v("sales_ranking", ra, basis="delivered", continuation=True, entity_op="reuse", domain_in_message=False,
           open_question_answer=_pick_of(pos), reference_positions=[pos], **SEPF)
    text, calls = rbot.say(v, "brand")
    args = _args(calls)
    assert args.get("brand_ids") and not args.get("company"), f"H16: the brand answer set the company: {args}"


# ------------------------------------------------------------------------------------------ crew re-check 6 Nov (round 5)
# No recorded objects reached this sandbox; each test names the parse shape it assumes (crew: replay the real step 8, 14,
# 16 and 1 objects through these to confirm).


@pytest.mark.usefixtures("all_on", "said_as_on")
@pytest.mark.parametrize("brands", [["Sorento", "Cabana"], ["Sorento"]], ids=["step8", "step14"])
@pytest.mark.parametrize("said_as", ["both", "brand"])
def test_k8_an_object_naming_the_company_and_the_brand_of_one_name_runs_both(rbot, world, brands, said_as) -> None:
    """Crew re-check steps 8 / 14a (after a clear: no company held): the object writes company Sorento AND brands with
    SORENTO. The object is final (round 6): both run, whatever the entity's said_as says. Round 5 let said_as brand drop
    the object's company (the CP-5 branch, `report_ask.py:3681` on dcd1fd81), so the display disagreed with the parse."""
    sorento, _m = world
    _hold(rbot, None, group_by="channel")
    ents = [_said("Sorento", said_as, "company, brand"), *([_ent("Cabana", "brand", "CABANA", "brands")] if "Cabana" in brands else [])]
    ra = _ra2(None, basis="delivered", group_by="channel", company=sorento, brands=brands, **SEP)
    v = _follow("sales_analysis", ra, *ents, group_by="channel", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "Sorento company, Sorento brand")
    assert _ran(calls), f"K8: nothing ran: {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID, f"K8 company ({said_as}): {args}"
    assert len(args.get("brand_ids") or []) >= len(brands), f"K8 brands: {args}"


@pytest.mark.usefixtures("all_on", "said_as_on")
@pytest.mark.parametrize("answer_company", [None, "Sorento"], ids=["object-company-null", "object-company-echo"])
def test_k16_a_brand_answer_to_the_company_or_brand_question_is_the_brand_across_every_company(
    rbot, world, answer_company
) -> None:
    """Crew re-check step 16: "Sorento total sale delivered September 2026" whose object also wrote company Sorento (the
    Known companies line) asks company or brand; "brand" then showed Company Sorento + Brand SORENTO. The brand answer
    replaces the company reading of that name: no company, whether the reply's object leaves the company null or echoes
    the asked name."""
    from tests.chatbot.test_report_totals_filters import _kind_slot, _option_position, _ra3

    _sorento_debtor_type(rbot)
    ra = _ra3(["Sorento"], basis="delivered", company="Sorento", **SEP)
    ra["frame"] = "total"
    first = _v("sales_report", ra, _said("Sorento", None, ""), basis="delivered", sales_company="Sorento",
               domain_in_message=True, **SEPF)
    text, calls = rbot.say(first, "Sorento total sale delivered September 2026")
    slot = _kind_slot(rbot)
    assert not _ran(calls) and slot.get("asking") == "kind", f"setup: {text!r} {_ran(calls)}"
    pos = _option_position(slot, "brand")
    ra2 = _ra3([], basis="delivered", company=answer_company, brands=["SORENTO"], **SEP)
    ra2["frame"] = "total"
    v = _v("sales_ranking", ra2, basis="delivered", continuation=True, entity_op="reuse", domain_in_message=False,
           open_question_answer=_pick_of(pos), reference_positions=[pos], **SEPF)
    text, calls = rbot.say(v, "brand")
    args = _args(calls)
    assert args.get("brand_ids") and not args.get("company"), f"K16: the brand answer kept the company: {args}"


@pytest.mark.usefixtures("all_on")
def test_k1_a_total_frame_beside_this_messages_own_axis_is_that_breakdown(rbot, world) -> None:
    """Crew re-check step 1 / fa-36: "Total sale delivered September 2026 Sorento company, Sorento brand, show dealer and
    project" parsed frame total WITH group_by channel on a fresh thread. The axis is this message's own (no report held,
    so not a copied one): the breakdown runs. A total over a copied held axis still drops it (G1b, AF-3)."""
    sorento, _m = world
    ra = _ra2("total", basis="delivered", group_by="channel", company=sorento, **SEP)
    v = _v("sales_report", ra, basis="delivered", group_by="channel", sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "Total sale delivered September 2026 Sorento company, show dealer and project")
    assert _args(calls).get("group_by") == "channel", f"K1: {_args(calls)}"


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("channel", [None, ALL], ids=["channel-null", "channel-all"])
def test_k1b_a_total_with_no_axis_in_the_object_takes_this_messages_own_axis(rbot, world, channel) -> None:
    """Crew re-check step 1 on v78: the object came back frame total with NO group_by, so the K1 rule never fired. The
    parse's top-level `group_by` is this message's own reading (prompt: from the current message only): a total whose
    object names no axis, beside this message's own axis that is not the held one and not a one-value slot, is that
    breakdown."""
    sorento, _m = world
    ra = _ra2("total", basis="delivered", group_by=None, company=sorento, brands=["SORENTO"], channel=channel, **SEP)
    v = _v("sales_report", ra, _ent("sorento", "brand", "SORENTO", "brand"), basis="delivered", group_by="channel",
           sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "Total sale delivered September 2026 Sorento company, Sorento brand, show dealer and project")
    args = _args(calls)
    assert args.get("group_by") == "channel" and args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), args


@pytest.mark.usefixtures("all_on")
def test_k1c_lock_a_total_with_no_axis_anywhere_stays_one_figure(rbot, world) -> None:
    sorento, _m = world
    ra = _ra2("total", basis="delivered", group_by=None, company=sorento, **SEP)
    v = _v("sales_report", ra, basis="delivered", group_by=None, sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "Total sale delivered September 2026 Sorento company")
    assert not _args(calls).get("group_by"), _args(calls)


# fa-16 / fa-20 / fa-36 as recorded objects (gold `parser_report_filter_all.jsonl`): the object the ALL prompt should write,
# and the miss crew recorded on the 6 Nov re-check, replayed through the engine on the world's names.


def _fa_clear(rbot, sorento, **slots: Any):
    _hold_all_kinds(rbot, sorento)
    every = {slot: _all_of(slot) for slot, *_rest in _KINDS.values()}
    every.update(slots)
    ra = _ra2(None, basis=None, group_by=None, measure=None, date_from=None, date_to=None, **every)
    return _args(rbot.say(_follow("sales_analysis", ra, basis=None, group_by=None), "clear")[1])


@pytest.mark.usefixtures("all_on")
@pytest.mark.parametrize("row", ["fa-16 tak payah filter apa2, semua", "fa-20 start over without any filter, same month"])
def test_fa16_fa20_the_gold_clear_all_object_clears_company_and_channel_too(rbot, world, row) -> None:
    sorento, _m = world
    args = _fa_clear(rbot, sorento)
    assert not args.get("company") and not args.get("channel"), f"{row}: {args}"
    assert args.get("basis") == "delivered" and args.get("group_by") == "month" and args.get("date_from") == "2026-09-01", args


@pytest.mark.usefixtures("all_on")
def test_fa16_fa20_the_recorded_miss_keeps_the_channel_because_the_object_kept_it(rbot, world) -> None:
    """Crew 6 Nov: fa-16 / fa-20 parsed channel "dealer" (and company) as held while clearing the lists. The code applies
    the object as written: the kept channel is the parser's, not a code drop or refill."""
    sorento, _m = world
    args = _fa_clear(rbot, sorento, channel="dealer")
    assert args.get("channel") == "dealer" and not args.get("brand_ids") and not args.get("customer_ids"), args


@pytest.mark.usefixtures("all_on")
def test_fa36_the_gold_step1_object_is_the_dealer_project_breakdown(rbot, world) -> None:
    sorento, _m = world
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company=sorento, brands=["SORENTO"], **SEP)
    v = _v("sales_analysis", ra, _ent("sorento", "brand", "SORENTO", "brand"), basis="delivered", group_by="channel",
           sales_company=sorento, domain_in_message=True, **SEPF)
    args = _args(rbot.say(v, "Total sale delivered September 2026 Sorento company, Sorento brand, show dealer and project")[1])
    assert args.get("group_by") == "channel" and args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), args
