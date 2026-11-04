"""Phase 2 RED tests: totals vs top-N, one name one filter, clear one filter, combined turn (lane CHATBOT-TOTALS-FILTERS).

`documentation/plans/chatbot/chatbot-totals-filters-acceptance-criteria.md` (AF, ON, CL, CT, HF, RB rows; the PENDING-Q2 and
PENDING-Q4 rows and the prompt-level BA rows are not here), plan `PLAN-chatbot-totals-filters-4nov.md` (M1 to M5).

Contract pinned here (nothing else is assumed), on the NEW report-ask path (`parser.REPORT_ASK_LINE`):
* `report_ask.frame`: "total" | "breakdown" | "ranking" | absent / null.
  total: one figure, no `group_by` in the report args, no count ask, no measure ask, a held axis / top N dropped.
  breakdown: `group_by` is the object's axis, every row, no count ask, no measure ask, even beside a stray message-level
  `rank_direction` "top" or `order_status` "sales_ranking". A frame with an axis beats a held axis.
  ranking: the count and the measure are asked only when missing. Absent / null: today, unchanged.
* `entities[].kind_said` "company" | "brand": when the object puts the SAME name (casefold) in two filter slots, the
  kind the message said keeps its slot and the other slot drops the name. Found from the tables, never from a name list.
* Clearing one filter on the new path: parser `broaden_axis` + `broaden_to` "all" + `scope_intent` "broaden" and the
  object omitting that filter. Only that filter goes; the held state after says so too.
* RB-1: `with_customer_groups`, `arg_names`, `_group_names` skip a non-UUID id (no DataError), the rest runs.

Real engine, report lane and MCP presenter (`bot.say(verdict, message)`); only the parser verdict and the MCP transport
are doubles. Harness, world and stubbed verdict shapes are those of `test_report_semantic_carry`. Invented data only.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.product import Brand
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID
from tests.chatbot.test_chat_state_parser_input import _fresh_prompt_cache  # noqa: F401 - fixture
from tests.chatbot.test_report_ask_lane import CUSTOMER_NAME, PRODUCT_CODE
from tests.chatbot.test_report_semantic_carry import (  # noqa: F401 - fixtures + helpers
    AGENT_1,
    TOOL,
    YR,
    Routing,
    _ent,
    _pick_of,
    _ra,
    _ran,
    _v,
    rbot,
    world,
)
from tests.chatbot.test_report_unify_routing import bot, console  # noqa: F401 - fixtures

TOP_N_Q = "How many?"
MEASURE_Q = "By quantity or by amount?"
SEP = dict(date_from="2026-09-01", date_to="2026-09-30")
SEPF = dict(date_filter_start="2026-09-01", date_filter_end="2026-09-30")
OCT = dict(date_from="2026-10-01", date_to="2026-10-09")
OCTF = dict(date_filter_start="2026-10-01", date_filter_end="2026-10-09")


# ------------------------------------------------------------------------------------------ helpers


def _ra2(frame: str | None = "__absent__", **kw: Any) -> dict[str, Any]:
    """The report_ask object plus the new `frame` key (left out entirely when "__absent__")."""
    ra = _ra(**kw)
    if frame != "__absent__":
        ra["frame"] = frame
    return ra


def _args(calls) -> dict[str, Any]:
    """The last report's args without the transport's own diagnostics."""
    ran = _ran(calls)
    assert ran, f"no report ran: {calls}"
    return {k: v for k, v in ran[-1].items() if k != "_diagnostics"}


def _frame(b: Routing) -> dict[str, Any]:
    focus = (b.console.session_vars or {}).get("focus") or {}
    return focus.get("sales_ranking_frame") or {}


def _asked(text: str) -> list[str]:
    return [q for q in (TOP_N_Q, MEASURE_Q, "Which period?", "Delivered") if q in text]


def _hold(b: Routing, sorento: str, *, group_by: str | None = "channel", entities: tuple = (), flat: dict | None = None,
          **ra_kw: Any) -> dict[str, Any]:
    """Turn 1 of every held scenario: a delivered September report that runs. Returns its args."""
    ra = _ra2(
        None, basis="delivered", group_by=group_by, measure="amount", company=sorento, **{**SEP, **ra_kw},
    )
    over = dict(basis="delivered", group_by=group_by, measure="amount", sales_company=sorento, domain_in_message=True, **SEPF)
    over.update(flat or {})
    status = "sales_analysis" if group_by else "sales_report"
    text, calls = b.say(_v(status, ra, *entities, **over), "held report")
    assert _ran(calls), f"setup: the held report did not run: {text!r}"
    return _args(calls)


def _follow(status: str, ra: dict[str, Any], *entities: dict[str, Any], **flat: Any) -> dict[str, Any]:
    """A follow-up verdict: continuation, the object is the whole ask after the message."""
    over = dict(continuation=True, entity_op="modify", basis="delivered", domain_in_message=True)
    over.update(flat)
    return _v(status, ra, *entities, **over)


def _widen(axis: str) -> dict[str, Any]:
    """The real B5-B7 parse of "all <kind>": the parser widens the axis to all."""
    return dict(broaden_axis=axis, broaden_to="all", scope_intent="broaden")


def _both_brands(b: Routing) -> None:
    """Mocha's own brand of the same name (ON-4 / ON-7: a second overlapping company + brand pair, from data)."""
    db = b.console.session_factory()
    try:
        db.add(Brand(id=str(uuid.uuid4()), brand_code="MOCHA", brand_name="Mocha", company_id=MOCHA_ID))
        db.commit()
    finally:
        db.close()


# ------------------------------------------------------------------------------------------ AF: ask frame (R1)


@pytest.mark.parametrize("noisy", [False, True], ids=["clean", "noisy_group_by_and_rank"])
def test_af1_a_total_with_a_brand_is_one_figure_with_no_count_or_measure_ask(rbot, world, noisy) -> None:
    """AF-1: "Total sale delivered 1/10-9/10/26 Sorento brand". Noisy = the live parse that read "brand" as an axis."""
    sorento, _m = world
    ra = _ra2("total", basis="delivered", group_by="brand" if noisy else None, brands=["Sorento"], **OCT)
    over = dict(basis="delivered", domain_in_message=True, **OCTF)
    if noisy:
        over.update(group_by="brand", rank_direction="top")
    status = "sales_ranking" if noisy else "sales_report"
    text, calls = rbot.say(_v(status, ra, _ent("sorento", "brand", "SORENTO", "brand"), **over), "Total sale delivered 1/10-9/10/26 Sorento brand")
    assert TOP_N_Q not in text and MEASURE_Q not in text, f"AF-1: a total was asked a ranking question: {text!r}"
    args = _args(calls)
    assert not args.get("group_by"), f"AF-1: a total ran with group_by {args.get('group_by')!r}"
    assert args.get("brand_ids") and args["basis"] == "delivered", args
    assert args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-09", args
    assert not _frame(rbot).get("group_by"), f"AF-1: the held state keeps an axis: {_frame(rbot)}"


def test_af2_show_dealer_and_project_is_a_breakdown_by_channel_with_no_count_or_measure_ask(rbot, world) -> None:
    """AF-2, the real C5 parse: a stray rank_direction top and order_status sales_ranking beside frame breakdown."""
    sorento, _m = world
    _hold(rbot, sorento, group_by="channel")
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company=sorento, **SEP)
    v = _follow("sales_ranking", ra, group_by="channel", rank_direction="top", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "show dealer and project")
    assert TOP_N_Q not in text and MEASURE_Q not in text, f"AF-2: a breakdown was asked a ranking question: {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "channel" and args["company"] == DEFAULT_COMPANY_ID, args
    assert args["basis"] == "delivered" and args["date_from"] == "2026-09-01", args
    assert _frame(rbot).get("group_by") == "channel", _frame(rbot)


def test_af3_total_sales_by_qty_drops_the_held_axis_and_top_n_and_keeps_the_rest(rbot, world) -> None:
    sorento, _m = world
    ra1 = _ra2(None, basis="delivered", group_by="product", top_n=10, measure="amount", company=sorento, **SEP)
    v1 = _v("sales_ranking", ra1, basis="delivered", group_by="product", top_n=10, measure="amount", rank_direction="top",
            sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v1, "top 10 products September delivered")
    assert _ran(calls) and _args(calls).get("top_n") == 10, f"setup: {text!r}"
    ra = _ra2("total", basis="delivered", measure="qty", company=sorento, **SEP)
    text, calls = rbot.say(_follow("sales_report", ra, measure="qty", sales_company=sorento, **SEPF), "i want total sales, by qty")
    assert TOP_N_Q not in text and MEASURE_Q not in text, f"AF-3: {text!r}"
    args = _args(calls)
    assert not args.get("group_by") and not args.get("top_n"), f"AF-3: the held axis or top N survived: {args}"
    assert args["company"] == DEFAULT_COMPANY_ID and args["basis"] == "delivered" and args["date_from"] == "2026-09-01", args
    frame = _frame(rbot)
    assert not frame.get("group_by") and not frame.get("top_n"), f"AF-3: the held state keeps the axis or top N: {frame}"
    assert frame.get("company") == DEFAULT_COMPANY_ID and frame.get("basis") == "delivered", frame


def test_af4_top_5_on_a_held_breakdown_ranks_the_channel_and_asks_no_measure_when_one_is_held(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by="channel")
    ra = _ra2("ranking", basis="delivered", group_by="channel", top_n=5, measure="amount", company=sorento, **SEP)
    v = _follow("sales_ranking", ra, group_by="channel", top_n=5, rank_direction="top", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "top 5")
    assert MEASURE_Q not in text and TOP_N_Q not in text, f"AF-4: {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "channel" and args.get("top_n") == 5, args
    assert _frame(rbot).get("top_n") == 5, _frame(rbot)


def test_af5_top_10_products_asks_only_the_measure(rbot, world) -> None:
    sorento, _m = world
    ra = _ra2("ranking", basis="delivered", group_by="product", top_n=10, company=sorento, **SEP)
    v = _v("sales_ranking", ra, basis="delivered", group_by="product", top_n=10, rank_direction="top", sales_company=sorento,
           domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "top 10 products September delivered")
    assert not _ran(calls), f"AF-5: ran before the measure was asked: {calls}"
    assert MEASURE_Q in text and TOP_N_Q not in text, f"AF-5: want only the measure question, got {text!r}"


def test_af_guard_no_frame_a_ranking_without_a_count_still_asks_the_count(rbot, world) -> None:
    """Frame absent: today's behaviour, byte for byte (the SC-13 case, no frame key at all)."""
    sorento, _m = world
    ra = _ra(basis="delivered", group_by="customer", measure="amount", company=sorento, **SEP)
    v = _v("sales_ranking", ra, basis="delivered", group_by="customer", measure="amount", rank_direction="top",
           sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "sorento customers ranking september delivered")
    assert not _ran(calls) and TOP_N_Q in text, (calls, text)


def test_af_guard_no_frame_a_plain_total_runs_with_no_axis(rbot, world) -> None:
    sorento, _m = world
    ra = _ra(basis="delivered", company=sorento, **SEP)
    text, calls = rbot.say(_v("sales_report", ra, basis="delivered", sales_company=sorento, domain_in_message=True, **SEPF), "sorento sales september delivered")
    args = _args(calls)
    assert not args.get("group_by") and args["company"] == DEFAULT_COMPANY_ID, (args, text)


# Owner ruling Q4: "all sale agents" is a breakdown by sales agent, every agent plus the grand total.

AF6_MSG = "Total sale for all sale agents on September 2026"


@pytest.mark.parametrize("noise", [{}, {"rank_direction": "top"}], ids=["clean", "stray_rank_direction"])
def test_af6a_all_sale_agents_on_a_fresh_thread_asks_the_basis_then_runs_every_agent_with_no_count_or_measure_ask(rbot, world, noise) -> None:
    from tests.chatbot.test_sales_account_type_lane import BASIS_Q

    ra = _ra2("breakdown", basis=None, group_by="sales_agent", **SEP)
    v1 = _v("sales_analysis", ra, group_by="sales_agent", domain_in_message=True, **SEPF, **noise)
    text, calls = rbot.say(v1, AF6_MSG)
    assert not _ran(calls) and text.strip() == BASIS_Q, f"AF-6a: want the basis question first, got {text!r}"
    ra2 = _ra2("breakdown", basis="invoiced", group_by="sales_agent", **SEP)
    v2 = _v("sales_ranking", ra2, basis="invoiced", continuation=True, entity_op="reuse", domain_in_message=False, **SEPF, **noise)
    text, calls = rbot.say(v2, "Invoiced")
    assert TOP_N_Q not in text and MEASURE_Q not in text, f"AF-6a: a breakdown was asked a ranking question: {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "sales_agent" and args["basis"] == "invoiced", args
    assert (args.get("top_n") or 0) >= 100, f"AF-6a: not every agent (top_n {args.get('top_n')!r}): {args}"
    assert "Total" in text, f"AF-6a: no grand total in the reply: {text!r}"
    assert _frame(rbot).get("group_by") == "sales_agent", _frame(rbot)


@pytest.mark.parametrize("noise", [{}, {"rank_direction": "top"}], ids=["clean", "stray_rank_direction"])
def test_af6b_all_sale_agents_on_a_held_thread_is_the_agent_breakdown_with_company_kept_and_no_basis_ask(rbot, world, noise) -> None:
    from tests.chatbot.test_sales_account_type_lane import BASIS_Q

    sorento, _m = world
    _hold(rbot, sorento, group_by="channel")
    ra = _ra2("breakdown", basis="delivered", group_by="sales_agent", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="sales_agent", sales_company=sorento, **SEPF, **_widen("sales_agent"), **noise)
    text, calls = rbot.say(v, AF6_MSG)
    assert BASIS_Q not in text and TOP_N_Q not in text and MEASURE_Q not in text, f"AF-6b: asked {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "sales_agent" and args["basis"] == "delivered", args
    assert args.get("company") == DEFAULT_COMPANY_ID and (args.get("top_n") or 0) >= 100, args
    assert _frame(rbot).get("group_by") == "sales_agent" and _frame(rbot).get("company") == DEFAULT_COMPANY_ID, _frame(rbot)


def test_af6c_the_same_ask_read_as_a_total_is_one_figure_with_no_axis(rbot, world) -> None:
    from tests.chatbot.test_sales_account_type_lane import BASIS_Q

    sorento, _m = world
    _hold(rbot, sorento, group_by="channel")
    ra = _ra2("total", basis="delivered", company=sorento, **SEP)
    v = _follow("sales_report", ra, sales_company=sorento, **SEPF, **_widen("sales_agent"))
    text, calls = rbot.say(v, AF6_MSG)
    assert BASIS_Q not in text and TOP_N_Q not in text and MEASURE_Q not in text, f"AF-6c: asked {text!r}"
    args = _args(calls)
    assert not args.get("group_by") and args["basis"] == "delivered" and args.get("company") == DEFAULT_COMPANY_ID, args
    assert not _frame(rbot).get("group_by"), _frame(rbot)


# ------------------------------------------------------------------------------------------ ON: one name, one filter (R2)


def _on_company(rbot, sorento: str, name: str, code: str, company_id: str, message: str, kind: str, *, group_by: str | None = "channel") -> tuple[str, dict[str, Any]]:
    """Held September delivered split; then "<name> <kind> only" with the real parse: the same name in company AND brands."""
    _hold(rbot, name, group_by=group_by)
    ra = _ra2(None, basis="delivered", group_by=group_by, measure="amount", company=name, brands=[code], **SEP)
    v = _follow("sales_analysis", ra, _ent(name.lower(), "brand", code, kind), group_by=group_by, measure="amount", sales_company=name, **SEPF)
    text, calls = rbot.say(v, message)
    return text, _args(calls)


def test_on1_company_only_keeps_the_company_and_no_brand(rbot, world) -> None:
    sorento, _m = world
    text, args = _on_company(rbot, sorento, "Sorento", "SORENTO", DEFAULT_COMPANY_ID, "sorento company only", "company")
    assert args.get("company") == DEFAULT_COMPANY_ID, args
    assert not args.get("brand_ids"), f"ON-1: the company word was also applied as a brand: {args.get('brand_ids')}"
    assert args.get("group_by") == "channel" and args["basis"] == "delivered" and args["date_from"] == "2026-09-01", args
    frame = _frame(rbot)
    assert not frame.get("brand_ids") and frame.get("company") == DEFAULT_COMPANY_ID and frame.get("group_by") == "channel", (
        f"ON-1: the held state keeps a brand: {frame}"
    )


def test_on2_brand_only_keeps_the_brand_and_adds_no_company(rbot, world) -> None:
    sorento, _m = world
    text, args = _on_company(rbot, sorento, "Sorento", "SORENTO", DEFAULT_COMPANY_ID, "Sorento brand only", "brand", group_by=None)
    assert args.get("brand_ids"), f"ON-2: the brand was dropped: {args}"
    assert "company" not in args, f"ON-2: a company filter was added for a brand: {args.get('company')}"
    assert args["basis"] == "delivered" and args["date_from"] == "2026-09-01", args
    frame = _frame(rbot)
    assert frame.get("brand_ids") and not frame.get("company"), f"ON-2: the held state: {frame}"


@pytest.mark.parametrize("kind", ["company", "brand"])
def test_on4_the_same_holds_for_mocha(rbot, world, kind) -> None:
    sorento, mocha = world
    _both_brands(rbot)
    group_by = "channel" if kind == "company" else None
    text, args = _on_company(rbot, sorento, mocha, "MOCHA", MOCHA_ID, f"mocha {kind} only", kind, group_by=group_by)
    if kind == "company":
        assert args.get("company") == MOCHA_ID and not args.get("brand_ids"), f"ON-4 company: {args}"
        assert not _frame(rbot).get("brand_ids"), _frame(rbot)
    else:
        assert args.get("brand_ids") and "company" not in args, f"ON-4 brand: {args}"
        assert _frame(rbot).get("brand_ids") and not _frame(rbot).get("company"), _frame(rbot)


def test_on7_overlap_is_read_from_the_data_a_pair_that_is_not_one_name_keeps_both_filters(rbot, world) -> None:
    """Company Sorento and brand Cabana are two names: kind_said brand must not drop the company (no name list in code)."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2(None, basis="delivered", company=sorento, brands=["Cabana"], **SEP)
    v = _follow("sales_report", ra, _ent("cabana", "brand", "CABANA", "brand"), sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "sorento cabana brand")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and len(args.get("brand_ids") or []) == 1, f"ON-7: {args}"


def test_on7_overlap_detection_covers_a_second_pair_from_the_data_mocha_company_and_brand(rbot, world) -> None:
    sorento, mocha = world
    _both_brands(rbot)
    ra = _ra2(None, basis="delivered", company=mocha, brands=["MOCHA"], **SEP)
    v = _v("sales_report", ra, _ent("mocha", "brand", "MOCHA", "company"), basis="delivered", sales_company=mocha,
           domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "mocha company only delivered september")
    args = _args(calls)
    assert args.get("company") == MOCHA_ID and not args.get("brand_ids"), f"ON-7: the Mocha pair was not found from the data: {args}"


def test_on6_a_word_in_both_tables_still_asks_brand_or_account_type(rbot, world) -> None:
    """ON-6 lock (#2105): Cabana sales Sep delivered, kind not said."""
    from tests.chatbot.test_sales_account_type_lane import QUESTION

    sorento, _m = world
    ra = _ra2(None, basis="delivered", company=sorento, brands=["Cabana"], **SEP)
    v = _v("sales_report", ra, _ent("cabana", "brand", "CABANA", None), basis="delivered", sales_company=sorento,
           domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "Cabana sales Sep delivered")
    assert not _ran(calls) and text.strip() == QUESTION, (calls, text)


# Owner ruling Q2 (c): a bare name that is BOTH a company the contact sees and a brand asks once which one.


def _bare_name(rbot, name: str = "sorento", code: str = "SORENTO", **over: Any) -> tuple[str, list]:
    ra = _ra2(None, basis="delivered", brands=[code], **SEP)
    v = _v("sales_report", ra, _ent(name, "brand", code, None), basis="delivered", domain_in_message=True, **SEPF, **over)
    return rbot.say(v, f"{name.capitalize()} total sale September 2026")


def _kind_slot(rbot) -> dict[str, Any]:
    return ((rbot.console.session_vars or {}).get("focus") or {}).get("required_ask") or {}


def _option_position(slot: dict[str, Any], word: str) -> int:
    for i, opt in enumerate(slot.get("options") or [], start=1):
        if word in {str(x).strip().lower() for x in (opt if isinstance(opt, (list, tuple)) else [opt])}:
            return i
    raise AssertionError(f"the kind question offers no {word!r} option: {slot.get('options')}")


def test_on3_a_bare_name_that_is_a_company_and_a_brand_asks_once_which_one(rbot, world) -> None:
    sorento, _m = world
    text, calls = _bare_name(rbot)
    assert not _ran(calls), f"ON-3: a report ran for a bare company/brand name: {_ran(calls)}"
    slot = _kind_slot(rbot)
    assert slot.get("ask") == "sales_ranking" and slot.get("asking") == "kind", f"ON-3: the kind question is not open: {slot.get('asking')!r} / {text!r}"
    shown = str(slot).lower()
    assert "sorento" in shown, f"ON-3: the question does not name the word: {slot}"
    assert "company" in text.lower() and "brand" in text.lower(), f"ON-3: the options must include company and brand: {text!r}"


def test_on5_a_bare_name_for_a_contact_who_sees_one_company_is_a_brand_with_no_question(rbot) -> None:
    text, calls = _bare_name(rbot)
    assert _kind_slot(rbot).get("asking") != "kind", f"ON-5: a one-company contact was asked: {text!r}"
    args = _args(calls)
    assert args.get("brand_ids") and "company" not in args, f"ON-5: {args}"


def test_on8_a_message_naming_both_kinds_applies_both_filters_with_no_question(rbot, world) -> None:
    sorento, _m = world
    ra = _ra2(None, basis="delivered", company=sorento, brands=["SORENTO"], **SEP)
    v = _v("sales_report", ra, _ent("sorento", "brand", "SORENTO", "company and brand"), basis="delivered",
           sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v, "sorento company and brand total sale September 2026")
    assert _kind_slot(rbot).get("asking") != "kind", f"ON-8: asked though both kinds were said: {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("brand_ids"), f"ON-8: want both filters, got {args}"
    frame = _frame(rbot)
    assert frame.get("company") == DEFAULT_COMPANY_ID and frame.get("brand_ids"), frame


@pytest.mark.parametrize("answer", ["company", "brand", "both"], ids=["on9_company", "on10_brand", "on11_both"])
def test_on9_10_11_the_answer_to_the_kind_question_applies_that_kind_and_keeps_the_rest(rbot, world, answer) -> None:
    sorento, _m = world
    text, calls = _bare_name(rbot)
    slot = _kind_slot(rbot)
    assert not _ran(calls) and slot.get("asking") == "kind", f"setup: the kind question was not asked: {text!r}"
    pos = _option_position(slot, answer)
    ra = _ra2(None, basis="delivered", brands=["SORENTO"], **SEP)
    v = _v("sales_ranking", ra, basis="delivered", continuation=True, entity_op="reuse", domain_in_message=False,
           open_question_answer=_pick_of(pos), reference_positions=[pos], **SEPF)
    text, calls = rbot.say(v, answer)
    assert _kind_slot(rbot).get("asking") != "kind", f"ON-9..11: the kind question was asked again: {text!r}"
    args = _args(calls)
    assert args["basis"] == "delivered" and args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    has_company = args.get("company") == DEFAULT_COMPANY_ID
    has_brand = bool(args.get("brand_ids"))
    assert (has_company, has_brand) == {"company": (True, False), "brand": (False, True), "both": (True, True)}[answer], (
        f"ON-{answer}: company {has_company}, brand {has_brand}: {args}"
    )


def test_on12_a_name_settled_in_an_earlier_turn_is_not_asked_again_and_the_held_company_stays(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2(None, basis="delivered", group_by="month", measure="amount", company=sorento, **SEP)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="month", measure="amount", sales_company=sorento, **SEPF), "by month")
    assert _kind_slot(rbot).get("asking") != "kind", f"ON-12: asked again: {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and not args.get("brand_ids"), f"ON-12: {args}"
    assert _frame(rbot).get("company") == DEFAULT_COMPANY_ID, _frame(rbot)


# ------------------------------------------------------------------------------------------ CL: clear one filter (R3)


def _hold_company_brand(rbot, sorento: str) -> dict[str, Any]:
    return _hold(rbot, sorento, group_by="channel", brands=["Sorento"], entities=(_ent("sorento", "brand", "SORENTO", "brand"),))


def _clear_brand(rbot, sorento: str, message: str) -> tuple[str, dict[str, Any]]:
    first = _hold_company_brand(rbot, sorento)
    assert first.get("brand_ids") and first.get("company") == DEFAULT_COMPANY_ID, f"setup: the held report: {first}"
    assert _frame(rbot).get("brand_ids"), f"setup: the held state has no brand: {_frame(rbot)}"
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **_widen("brand"))
    text, calls = rbot.say(v, message)
    assert not _asked(text), f"a clear asked something: {text!r}"
    return text, _args(calls)


@pytest.mark.parametrize("message", ["all brands", "clear the brand filter", "brand is all brand"], ids=["cl1", "cl2", "cl3"])
def test_cl_1_2_3_clearing_the_brand_keeps_company_split_period_and_basis(rbot, world, message) -> None:
    sorento, _m = world
    text, args = _clear_brand(rbot, sorento, message)
    assert not args.get("brand_ids"), f"CL: the brand survived: {args.get('brand_ids')}"
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("group_by") == "channel", args
    assert args["basis"] == "delivered" and args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    frame = _frame(rbot)
    assert not frame.get("brand_ids"), f"CL: the held state keeps the brand: {frame}"
    assert frame.get("company") == DEFAULT_COMPANY_ID and frame.get("group_by") == "channel" and frame.get("basis") == "delivered", frame
    assert frame.get("date_from") == "2026-09-01", frame


def test_cl4_all_customers_drops_the_customer_and_keeps_the_rest(rbot, world) -> None:
    sorento, _m = world
    first = _hold(rbot, sorento, group_by="channel", brands=["Sorento"], customers=[CUSTOMER_NAME],
                  entities=(_ent("sorento", "brand", "SORENTO", "brand"), _ent(CUSTOMER_NAME, "customer")))
    assert first.get("customer_ids") and first.get("brand_ids"), f"setup: {first}"
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, brands=["Sorento"], **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **_widen("customer"))
    text, calls = rbot.say(v, "all customers")
    assert not _asked(text), text
    args = _args(calls)
    assert not args.get("customer_ids"), f"CL-4: the customer survived: {args.get('customer_ids')}"
    assert args.get("brand_ids") == first["brand_ids"] and args.get("company") == DEFAULT_COMPANY_ID, args
    assert not _frame(rbot).get("customer_ids") and _frame(rbot).get("brand_ids"), _frame(rbot)


#: kind -> (the object list / slot that holds it, the entity that names it, the broaden axis, the route arg, the frame key)
_KINDS = {
    "brand": ("brands", lambda: _ent("sorento", "brand", "SORENTO", "brand"), "brand", "brand_ids", "brand_ids"),
    "customer": ("customers", lambda: _ent(CUSTOMER_NAME, "customer"), "customer", "customer_ids", "customer_ids"),
    "product": ("products", lambda: _ent(PRODUCT_CODE, "product"), "product", "product_code", "product_code"),
    "category": ("categories", lambda: _ent("ZZT CATEGORY", "category"), "category", "category_ids", "category_ids"),
    "agent": ("sales_agents", lambda: _ent(AGENT_1, "sales_agent"), "sales_agent", "sales_agent_ids", "sales_agent_ids"),
    "account_type": ("account_types", lambda: _ent("ceramic", "account_type", None, "account type"), "account_type", "account_types", "account_types"),
    "channel": ("channel", None, "channel", "channel", "channel"),
    "company": ("company", None, "company", "company", "company"),
}
_HELD_WORDS = dict(
    brands=["Sorento"], customers=[CUSTOMER_NAME], products=[PRODUCT_CODE], categories=["ZZT CATEGORY"], sales_agents=[AGENT_1],
    account_types=["ceramic"], channel="dealer",
)


@pytest.mark.parametrize("kind", list(_KINDS))
def test_cl5_all_of_a_kind_drops_only_that_filter(rbot, world, kind) -> None:
    sorento, _m = world
    slot, _ent_of, axis, arg, frame_key = _KINDS[kind]
    held_ents = tuple(f() for k, (_s, f, _a, _b, _c) in _KINDS.items() if f is not None)
    first = _hold(rbot, sorento, group_by="month", entities=held_ents, **_HELD_WORDS)
    held_frame = dict(_frame(rbot))
    assert first.get(arg) not in (None, [], ""), f"setup: the held report has no {kind} ({arg}): {first}"
    # The rest of the ask, restated by the object each turn; this kind left out (the real B5-B7 parses).
    words = {**_HELD_WORDS, "company": sorento}
    ra_kw = {k: v for k, v in words.items() if k != slot}
    ra = _ra2(None, basis="delivered", group_by="month", measure="amount", **ra_kw, **SEP)
    kept_ents = tuple(f() for k, (_s, f, _a, _b, _c) in _KINDS.items() if f is not None and k != kind)
    flat = dict(group_by="month", measure="amount", sales_company=None if kind == "company" else sorento, **SEPF, **_widen(axis))
    if kind != "channel":
        flat["sales_channel"] = "dealer"
    text, calls = rbot.say(_follow("sales_analysis", ra, *kept_ents, **flat), f"all {kind}")
    assert not _asked(text), f"CL-5 {kind}: asked {text!r}"
    args = _args(calls)
    assert not args.get(arg), f"CL-5 {kind}: the filter survived in the report: {arg}={args.get(arg)}"
    frame = _frame(rbot)
    assert not frame.get(frame_key), f"CL-5 {kind}: the held state keeps it: {frame_key}={frame.get(frame_key)}"
    for other, (_s, _f, _a, other_arg, other_key) in _KINDS.items():
        if other == kind:
            continue
        if other == "brand" and kind == "account_type" or other == "account_type" and kind == "brand":
            pass  # still checked: only the asked filter may go
        assert args.get(other_arg) == first.get(other_arg), f"CL-5 {kind}: also lost {other} ({other_arg}): {args.get(other_arg)!r} vs {first.get(other_arg)!r}"
        assert frame.get(other_key) == held_frame.get(other_key), f"CL-5 {kind}: the held state also lost {other}: {frame.get(other_key)!r}"


def test_cl6_all_brands_with_no_brand_held_is_a_no_op(rbot, world) -> None:
    sorento, _m = world
    first = _hold(rbot, sorento, group_by="channel")
    held = dict(_frame(rbot))
    ra = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF, **_widen("brand"))
    text, calls = rbot.say(v, "all brands")
    assert not _asked(text), f"CL-6: a no-op asked something: {text!r}"
    assert _args(calls) == first, f"CL-6: the report changed:\n{_args(calls)}\nvs\n{first}"
    assert {k: v for k, v in _frame(rbot).items() if k != "shown"} == {k: v for k, v in held.items() if k != "shown"}, _frame(rbot)


def test_cl7_start_over_clears_everything(rbot, world) -> None:
    sorento, _m = world
    _hold_company_brand(rbot, sorento)
    v = _v("sales_report", None, entity_op="clear", topic_reset=True, domain_in_message=False)
    text, calls = rbot.say(v, "start over")
    frame = _frame(rbot)
    assert not frame.get("brand_ids") and not frame.get("company") and not frame.get("group_by"), f"CL-7: {frame}"
    assert not any(a.get("brand_ids") or a.get("company") for a in _ran(calls)), f"CL-7: a report ran with held filters: {calls}"


# ------------------------------------------------------------------------------------------ CT: combined turn (R4)


def test_ct1_company_only_and_show_dealer_and_project_apply_in_one_reply(rbot, world) -> None:
    """CT-1 lock: company + split in one object, no overlap noise."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v = _follow("sales_analysis", ra, group_by="channel", measure="amount", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "sorento company only, show dealer and project")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("group_by") == "channel", args
    assert _frame(rbot).get("company") == DEFAULT_COMPANY_ID and _frame(rbot).get("group_by") == "channel", _frame(rbot)


def test_ct1_the_real_parse_company_only_beside_the_split_adds_no_brand_and_no_count_ask(rbot, world) -> None:
    """CT-1 real parse (C4/C5): the company word also sits in brands, the split carries a stray rank_direction."""
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="channel", company=sorento, brands=["SORENTO"], **SEP)
    v = _follow("sales_ranking", ra, _ent("sorento", "brand", "SORENTO", "company"), group_by="channel", rank_direction="top",
                sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "sorento company only, show dealer and project")
    assert TOP_N_Q not in text and MEASURE_Q not in text, f"CT-1: {text!r}"
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID and args.get("group_by") == "channel", args
    assert not args.get("brand_ids"), f"CT-1: the company word also became a brand: {args.get('brand_ids')}"


def test_ct2_a_typed_axis_in_the_object_beats_the_held_axis_over_an_open_count_question(rbot, world) -> None:
    sorento, _m = world
    ra1 = _ra2(None, basis="delivered", group_by="channel", measure="amount", company=sorento, **SEP)
    v1 = _v("sales_ranking", ra1, basis="delivered", group_by="channel", measure="amount", rank_direction="top",
            sales_company=sorento, domain_in_message=True, **SEPF)
    text, calls = rbot.say(v1, "top channels september delivered")
    assert not _ran(calls) and TOP_N_Q in text, f"setup: want the open count question, got {text!r}"
    ra = _ra2("breakdown", basis="delivered", group_by="brand", measure="amount", company=sorento, **SEP)
    v = _follow("sales_ranking", ra, group_by="brand", measure="amount", sales_company=sorento, **SEPF)
    text, calls = rbot.say(v, "break it down by brand")
    assert TOP_N_Q not in text, f"CT-2: the count was asked again: {text!r}"
    args = _args(calls)
    assert args.get("group_by") == "brand", f"CT-2: want a brand breakdown, got group_by {args.get('group_by')!r}"
    assert _frame(rbot).get("group_by") == "brand", _frame(rbot)


def test_ct3_a_new_month_and_a_new_axis_apply_together(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("breakdown", basis="delivered", group_by="brand", measure="amount", company=sorento, **OCT)
    text, calls = rbot.say(_follow("sales_analysis", ra, group_by="brand", measure="amount", sales_company=sorento, **OCTF), "October, by brand")
    assert TOP_N_Q not in text, text
    args = _args(calls)
    assert args.get("group_by") == "brand" and args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-09", args
    frame = _frame(rbot)
    assert frame.get("group_by") == "brand" and frame.get("date_from") == "2026-10-01", frame


# ------------------------------------------------------------------------------------------ HF: held filters on a new question (Q3)


def test_hf1_a_held_customer_stays_on_a_complete_new_question_and_the_header_lists_it(rbot, world) -> None:
    sorento, _m = world
    first = _hold(rbot, sorento, group_by=None, customers=[CUSTOMER_NAME], entities=(_ent(CUSTOMER_NAME, "customer"),))
    assert first.get("customer_ids"), f"setup: {first}"
    ra = _ra2("total", basis="delivered", brands=["Sorento"], **OCT)
    v = _v("sales_report", ra, _ent("sorento", "brand", "SORENTO", "brand"), basis="delivered", domain_in_message=True, **OCTF)
    text, calls = rbot.say(v, "Total sale deliver for 1/10-9/10/26 Sorento brand")
    args = _args(calls)
    assert args.get("customer_ids") == first["customer_ids"] and args.get("brand_ids"), f"HF-1: {args}"
    assert _frame(rbot).get("customer_ids") == first["customer_ids"], _frame(rbot)
    assert CUSTOMER_NAME in text or CUSTOMER_NAME in str(_frame(rbot).get("names")), f"HF-1: the customer is not named: {text!r}"


def test_hf2_a_held_company_stays_and_no_brand_the_user_never_said_appears(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    ra = _ra2("total", basis="delivered", **SEP)
    v = _v("sales_report", ra, basis="delivered", domain_in_message=True, **SEPF, **_widen("sales_agent"))
    text, calls = rbot.say(v, "Total sale for all sale agents on September 2026")
    args = _args(calls)
    assert args.get("company") == DEFAULT_COMPANY_ID, f"HF-2: the held company was dropped: {args}"
    assert not args.get("brand_ids"), f"HF-2: a brand appeared: {args.get('brand_ids')}"
    assert _frame(rbot).get("company") == DEFAULT_COMPANY_ID and not _frame(rbot).get("brand_ids"), _frame(rbot)


# ------------------------------------------------------------------------------------------ RB: robustness (#2105 follow-up)

NOT_A_UUID = "not-a-uuid"


def test_rb1_with_customer_groups_skips_a_non_uuid_id(rbot, world) -> None:
    from tests._mc_lookup_seed import customer

    from app.services.chatbot.lanes.business import report_ask

    db = rbot.console.session_factory()
    try:
        real = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZ RB1 TRADING").id
        db.commit()
        out = report_ask.with_customer_groups(db, {"customer_ids": [NOT_A_UUID, real]})
        assert real in out["customer_ids"], out
    finally:
        db.close()


def test_rb1_arg_names_skips_a_non_uuid_id(rbot, world) -> None:
    from tests._mc_lookup_seed import customer

    from app.services.chatbot.lanes.business import report_ask

    db = rbot.console.session_factory()
    try:
        real = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZ RB1 NAMES TRADING").id
        db.commit()
        names = report_ask.arg_names(db, {"customer_ids": [NOT_A_UUID, real], "brand_ids": [NOT_A_UUID], "company": DEFAULT_COMPANY_ID})
        assert names["customer_ids"].get(real) == "ZZ RB1 NAMES TRADING" and NOT_A_UUID not in names["customer_ids"], names
        assert not names.get("brand_ids"), names
    finally:
        db.close()


def test_rb1_group_names_skips_a_non_uuid_id(rbot, world) -> None:
    from tests._mc_lookup_seed import customer

    from app.services.chatbot.lanes.business import report_ask

    db = rbot.console.session_factory()
    try:
        real = customer(db, company_id=DEFAULT_COMPANY_ID, name="ZZ RB1 GROUP TRADING").id
        db.commit()
        assert report_ask._group_names(db, [NOT_A_UUID, real]) == {}
    finally:
        db.close()


def test_rb1_a_held_non_uuid_customer_id_does_not_break_the_next_report(rbot, world) -> None:
    sorento, _m = world
    _hold(rbot, sorento, group_by=None)
    frame = rbot.console.session_vars["focus"]["sales_ranking_frame"]
    frame["customer_ids"] = [NOT_A_UUID]
    frame.setdefault("names", {})["customer_ids"] = {NOT_A_UUID: "ZZ BAD ID TRADING"}
    ra = _ra2(None, basis="delivered", company=sorento, **OCT)
    text, calls = rbot.say(_follow("sales_report", ra, sales_company=sorento, **OCTF), "and 1 to 9 october")
    assert _ran(calls), f"RB-1: the report did not run after a bad held id: {text!r}"
    assert NOT_A_UUID not in str(_ran(calls)[-1].get("customer_ids")), _ran(calls)[-1]
