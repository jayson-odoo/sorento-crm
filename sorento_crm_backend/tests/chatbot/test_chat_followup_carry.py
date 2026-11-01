"""CHATBOT-FOLLOWUP-CARRY (owner ruling, 1 Nov 2026; PLAN-chatbot-followup-carry-1nov.md): a follow-up over a held customer
(no new customer named, no topic reset) keeps that customer, all its picked ledgers and the held period unless the message
changes it. A new customer, an explicit "all customers" or a topic reset replaces it.

The parses are the live parser's, measured on the crew copy (prompt v189) from the session right after the report: every run
of "how about ordered", "and delivered?" and "what about last month" named no customer, and the report lost it.

Engine harness: `test_new_ask_drops_sales_channel.chat` (real `engine.run_turn` and gate, Postgres; parser, access, resolver and
MCP faked), on the seed and turns of `test_chat_pick_carry`. Fake customers only (public repo).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot import contracts
from app.services.chatbot.lanes.business import report_ask
from app.services.chatbot.lanes.business.services import ResolveGateServices
from tests.chatbot._sales_pick_helpers import _pick
from tests.chatbot.conftest import validating_resolve_entity
from tests.chatbot.test_chat_pick_carry import (
    BASIS_QUESTION,
    DEALER_B,
    OCT_2026,
    PICKED,
    SHARED_CODE,
    _seed,
    _services,
    _t1,
    _t2,
    _three_turns,
)
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_new_ask_drops_sales_channel import _report_calls, _reply, chat  # noqa: F401  (fixture)

SEP_2026 = {"date_mode": "month", "date_filter_start": "2026-09-01", "date_filter_end": "2026-09-30"}
COMPANY_QUESTION = "Sorento or Mocha?"
NEW_SUBJECT = {"op": "new_subject"}
#: A carried customer echoed beside the follow-up, as the parser does on some runs: the first picked ledger's code, the one
#: the option carries. In the other company that code is a different customer (#2064).
CARRIED = {"raw": SHARED_CODE, "hint": "customer", "canonical_code": None, "current_message": False, "confident": True}


def _follow(**over: Any) -> dict[str, Any]:
    """A follow-up's parse as measured: no entity, `reuse`, no reset, no refine flag, no axis, the sales label."""
    fields: dict[str, Any] = dict(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="sales_analysis",
        basis=None, sales_basis=None, sales_channel=None, sales_company=None, entities=[], entity_op="reuse",
        domain_in_message=False, topic_reset=False, group_by=None,
    )
    fields.update(over)
    return _parser_output(**fields)


def _ordered(**over: Any) -> dict[str, Any]:
    return _follow(basis="ordered", sales_basis="ordered", **over)


def _delivered(**over: Any) -> dict[str, Any]:
    return _follow(order_status="sales_report", basis="delivered", sales_basis="delivered", **over)


def _last_month(**over: Any) -> dict[str, Any]:
    return _follow(order_status="sales_report", **SEP_2026, **over)


def _reported(chat, session_factory, tag: str):
    """The owner's three turns: the report on every picked ledger, invoiced, October, channel dealer."""
    ids, args = _three_turns(chat, session_factory, tag, _t2())
    assert sorted(args["customer_ids"]) == sorted(ids[k] for k in PICKED), args
    return ids, _services(ids)


def _picked_ids(ids: dict[str, str]) -> list[str]:
    return sorted(ids[k] for k in PICKED)


def _ran_once(result: Any, captured: Any) -> dict[str, Any]:
    calls = _report_calls(captured)
    assert len(calls) == 1, f"the follow-up asked instead of running: {_reply(result)!r}, {captured}"
    return calls[0]


def _slot_args(chat) -> dict[str, Any]:
    focus = chat.session().get("focus") or {}
    return ((focus.get("required_ask") or {}).get("extras") or {}).get("args") or {}


# ------------------------------------------------------------------ the owner's follow-ups


@pytest.mark.parametrize("entity_op", ["reuse", "modify", "replace_combine"])
def test_f1_how_about_ordered_keeps_the_customer_and_the_period(chat, session_factory, entity_op):
    """The owner's run: reply "Sorento or Mocha?", the slot holding no customer. `modify` is the run that asked "Which period?"."""
    ids, services = _reported(chat, session_factory, f"f1-{entity_op}")
    result, captured = chat(_ordered(entity_op=entity_op), "how about ordered", f"ZZT-fc-f1-{entity_op}", resolve_services=services)
    assert _reply(result).strip() != COMPANY_QUESTION, "no company question: the held customer is the subject"
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), args
    assert args["basis"] == "ordered", args
    assert args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-31", args
    assert args.get("channel") == "dealer", args


def test_f1b_a_carried_code_echo_and_the_month_restated_change_nothing(chat, session_factory):
    ids, services = _reported(chat, session_factory, "f1b")
    result, captured = chat(_ordered(entities=[CARRIED], **OCT_2026), "how about ordered", "ZZT-fc-f1b", resolve_services=services)
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), "exactly the pick: never the other company's row of the code"
    assert args["basis"] == "ordered", args


def test_f2_and_delivered_keeps_the_customer_and_the_period(chat, session_factory):
    ids, services = _reported(chat, session_factory, "f2")
    result, captured = chat(_delivered(), "and delivered?", "ZZT-fc-f2", resolve_services=services)
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), args
    assert args["basis"] == "delivered", args
    assert args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-31", args


def test_f3_what_about_last_month_keeps_the_customer_and_changes_only_the_period(chat, session_factory):
    """The message names a period and no basis: the basis on screen stays (S6c, what `_refine` keeps), and the reply's header
    names it, so it is not a silent default."""
    ids, services = _reported(chat, session_factory, "f3")
    result, captured = chat(_last_month(), "what about last month", "ZZT-fc-f3", resolve_services=services)
    assert _reply(result).strip() != BASIS_QUESTION, "the basis on screen is held, not asked"
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args
    assert args["basis"] == "invoiced", args


def test_f3b_the_analysis_label_with_no_basis_is_the_same_follow_up(chat, session_factory):
    ids, services = _reported(chat, session_factory, "f3b")
    result, captured = chat(_last_month(order_status="sales_analysis"), "what about last month", "ZZT-fc-f3b", resolve_services=services)
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


def test_f4_a_chain_of_follow_ups_keeps_exactly_the_picked_ledgers(chat, session_factory):
    """Each report holds what the one before it ran on, so the third is still the pick, and only the period it changed moved."""
    ids, services = _reported(chat, session_factory, "f4")
    chat(_ordered(), "how about ordered", "ZZT-fc-f4-1", resolve_services=services)
    chat(_last_month(), "what about last month", "ZZT-fc-f4-2", resolve_services=services)
    result, captured = chat(_delivered(), "and delivered?", "ZZT-fc-f4-3", resolve_services=services)
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), args
    assert ids["stranger"] not in args["customer_ids"], args
    assert args["basis"] == "delivered", args
    assert args["date_from"] == "2026-09-01" and args["date_to"] == "2026-09-30", args


def test_f5_a_new_axis_over_the_total_keeps_the_customer(chat, session_factory):
    """"by product": `reuse`, the product axis, a breakdown. Measured: the slot kept the channel and dropped the customer."""
    ids, services = _reported(chat, session_factory, "f5")
    result, captured = chat(_follow(group_by="product", by_words="by product"), "by product", "ZZT-fc-f5", resolve_services=services)
    args = _ran_once(result, captured)
    assert sorted(args.get("customer_ids") or []) == _picked_ids(ids), args
    assert args.get("group_by") == "product" and args["basis"] == "invoiced", args
    assert args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-31", args


# ------------------------------------------------------------------ a ranking held for a customer


def _one_customer(ids: dict[str, str]) -> ResolveGateServices:
    row = {"entity_type": "customer", "canonical_code": "300-ZZ59", "uuid": ids["dealer_b"], "company_code": "SRT",
           "display": {"customer_name": DEALER_B}}

    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        tokens = body.get("tokens") or []
        return {"tokens": tokens, "resolutions": [{"token": t, "matches": [row]} for t in tokens], "unresolved_tokens": []}

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve),
        probe=lambda **_: {"items": [], "has_result": False},
    )


def _ranked_for_one_customer(chat, session_factory, tag: str):
    ids = _seed(session_factory)
    services = _one_customer(ids)
    t1 = _parser_output(
        message_type="business_query", domain_hint="order", intent_hint="check_order", order_status="top_selling",
        basis="delivered", top_n=5, rank_by="amount", measure="amount", domain_in_message=True, entity_op="replace_combine",
        entities=[{"raw": "zz demo bath", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}],
        **OCT_2026,
    )
    result, captured = chat(t1, "zz demo bath top 5 products oct by amount delivered", f"ZZT-fc-{tag}-1", resolve_services=services)
    args = _ran_once(result, captured)
    assert args.get("customer_ids") == [ids["dealer_b"]] and args.get("group_by") == "product", args
    return ids, services


def test_r1_a_follow_up_over_a_held_ranking_keeps_the_customer_and_the_period(chat, session_factory):
    """Measured: `ranking_refine` null, no axis, the sales label. Reply "Sorento or Mocha?", the slot holding no customer."""
    ids, services = _ranked_for_one_customer(chat, session_factory, "r1")
    result, captured = chat(_ordered(), "how about ordered", "ZZT-fc-r1-2", resolve_services=services)
    args = _ran_once(result, captured)
    assert args.get("customer_ids") == [ids["dealer_b"]], args
    assert args["basis"] == "ordered", args
    assert args["date_from"] == "2026-10-01" and args["date_to"] == "2026-10-31", args


def test_r2_a_new_axis_over_a_held_ranking_keeps_the_customer(chat, session_factory):
    ids, services = _ranked_for_one_customer(chat, session_factory, "r2")
    result, captured = chat(_follow(group_by="month", by_words="by month"), "by month", "ZZT-fc-r2-2", resolve_services=services)
    args = _ran_once(result, captured)
    assert args.get("customer_ids") == [ids["dealer_b"]], args
    assert args.get("group_by") == "month", args


# ------------------------------------------------------------------ what replaces it


def _named_customer(**over: Any) -> dict[str, Any]:
    entity = {"raw": "zz demo bath", "hint": "customer", "canonical_code": None, "current_message": True, "confident": True}
    return _ordered(entities=[entity], entity_op="replace_combine", **OCT_2026, **over)


@pytest.mark.parametrize("entity_op", ["replace_combine", "reuse", "modify"])
def test_g1_guard_a_new_customer_replaces_the_held_one(chat, session_factory, entity_op):
    ids, _services_a = _reported(chat, session_factory, f"g1-{entity_op}")
    parse = _named_customer()
    parse["entity_op"] = entity_op
    result, captured = chat(parse, "how about zz demo bath", f"ZZT-fc-g1-{entity_op}", resolve_services=_one_customer(ids))
    args = _ran_once(result, captured)
    assert args.get("customer_ids") == [ids["dealer_b"]], "only the customer named: nothing of the held one"


@pytest.mark.parametrize("entity_op", ["reuse", "replace_combine"])
def test_g2_all_customers_drops_the_held_customer(chat, session_factory, entity_op):
    """Measured: "how about all customers" and "total for all customers" read `broaden_axis` customer, `broaden_to` all."""
    ids, services = _reported(chat, session_factory, f"g2-{entity_op}")
    parse = _ordered(entity_op=entity_op, broaden_axis="customer", broaden_to="all", **OCT_2026)
    result, captured = chat(parse, "how about all customers", f"ZZT-fc-g2-{entity_op}", resolve_services=services)
    assert _report_calls(captured) == [], captured
    assert _reply(result).strip() == COMPANY_QUESTION, _reply(result)
    assert not _slot_args(chat).get("customer_ids"), _slot_args(chat)


def test_g2b_all_customers_on_a_refine_drops_the_held_customer(chat, session_factory):
    ids, services = _reported(chat, session_factory, "g2b")
    parse = _ordered(ranking_refine=True, broaden_axis="customer", broaden_to="all", **OCT_2026)
    result, captured = chat(parse, "how about all customers", "ZZT-fc-g2b", resolve_services=services)
    assert not any(args.get("customer_ids") for args in _report_calls(captured)), captured
    assert not _slot_args(chat).get("customer_ids"), _slot_args(chat)


def test_g3_guard_a_topic_reset_drops_the_customer_and_the_period(chat, session_factory):
    """Measured: "start over, total sales oct delivered" reads `entity_op` clear and `topic_reset` true."""
    ids, services = _reported(chat, session_factory, "g3")
    parse = _follow(entity_op="clear", topic_reset=True, sales_basis="delivered", basis="delivered")
    result, captured = chat(parse, "start over, total delivered", "ZZT-fc-g3", resolve_services=services)
    assert _report_calls(captured) == [], captured
    held = _slot_args(chat)
    assert not held.get("customer_ids"), held
    values = ((chat.session().get("focus") or {}).get("required_ask") or {}).get("values") or {}
    assert "period" not in values, f"a reset carries no period: {values}"


@pytest.mark.parametrize("entity_op", ["replace", "replace_combine", "reuse"])
def test_g4_guard_the_parser_s_new_subject_op_carries_nothing(chat, session_factory, entity_op):
    ids, services = _reported(chat, session_factory, f"g4-{entity_op}")
    parse = _ordered(entity_op=entity_op, state_changes=[NEW_SUBJECT], **OCT_2026)
    result, captured = chat(parse, "total ordered oct", f"ZZT-fc-g4-{entity_op}", resolve_services=services)
    assert not any(args.get("customer_ids") for args in _report_calls(captured)), captured
    assert not _slot_args(chat).get("customer_ids"), _slot_args(chat)


def test_g5_guard_a_customer_axis_is_never_filtered_to_the_held_customer(chat, session_factory):
    """"top customers": the customer is what is ranked. The axis's own filter is not held, as for every other axis."""
    ids, services = _reported(chat, session_factory, "g5")
    parse = _follow(order_status="sales_ranking", group_by="customer", by_words="customers", top_n=5, measure="amount", rank_by="amount", basis="ordered", **OCT_2026)
    result, captured = chat(parse, "top 5 customers", "ZZT-fc-g5", resolve_services=services)
    assert not any(args.get("customer_ids") for args in _report_calls(captured)), captured
    assert not _slot_args(chat).get("customer_ids"), _slot_args(chat)


def test_g6_guard_a_pick_answering_a_new_ask_is_that_customer_never_the_held_one(chat, session_factory):
    ids, services = _reported(chat, session_factory, "g6")
    chat(_t1(), "Dealer zz demo oct total sales", "ZZT-fc-g6-1", resolve_services=services)
    assert (chat.session().get("open_question") or {}).get("kind") == "customer_pick"
    chat(_t2() | {"open_question_answer": _pick(2)}, "2", "ZZT-fc-g6-2", resolve_services=services)
    assert _slot_args(chat).get("customer_ids") == [ids["dealer_b"]], _slot_args(chat)


def test_g7_guard_my_sales_is_never_filtered_to_the_held_customer(chat, session_factory):
    ids, services = _reported(chat, session_factory, "g7")
    result, captured = chat(_ordered(self_reference=True, **OCT_2026), "how about my sales", "ZZT-fc-g7", resolve_services=services)
    assert not set(ids[k] for k in PICKED) & {u for args in _report_calls(captured) for u in args.get("customer_ids") or []}, captured
    assert not set(ids[k] for k in PICKED) & set(_slot_args(chat).get("customer_ids") or []), _slot_args(chat)


# ------------------------------------------------------------------ the stamp


U1, U2 = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"
TOTAL = {"sort": "desc", "basis": "invoiced", "customer_ids": [U1, U2], "date_from": "2026-10-01", "date_to": "2026-10-31"}


def _focus(frame: dict[str, Any] | None = None, domains: tuple[str, ...] = (contracts.SALES_DOMAIN,)) -> SimpleNamespace:
    return SimpleNamespace(sales_ranking_frame=frame, domains=list(domains), date_window=None, products=[])


def _verdict(entity_op: str, *entities: dict[str, Any]) -> dict[str, Any]:
    return {"order_status": report_ask.ASK_NAME, "entity_op": entity_op, "entities": list(entities), "topic_reset": False}


def _stamp(verdict: dict[str, Any], focus: SimpleNamespace) -> dict[str, Any] | None:
    return report_ask.with_held(verdict, focus, open_ask=None, replaced=None).get(report_ask.HELD_KEY)


NAMED = {"raw": "another", "hint": "customer", "current_message": True}
A_PRODUCT = {"raw": "SRT1", "hint": "product", "current_message": True}


@pytest.mark.parametrize("entity_op", ["reuse", "modify", "replace_combine"])
def test_u1_the_stamp_carries_the_held_customer_and_the_basis(entity_op):
    held = _stamp(_verdict(entity_op), _focus(TOTAL))
    assert held and held["customer_ids"] == [U1, U2] and held["basis"] == "invoiced" and held["date_from"] == "2026-10-01", held


def test_u2_a_new_product_keeps_the_held_customer_as_the_parser_s_table_says():
    held = _stamp(_verdict("replace_combine", A_PRODUCT), _focus(TOTAL))
    assert held and held["customer_ids"] == [U1, U2], held


@pytest.mark.parametrize("entity_op", ["modify", "replace_combine"])
def test_u3_guard_a_customer_named_is_no_follow_up_on_these_ops(entity_op):
    assert _stamp(_verdict(entity_op, NAMED), _focus(TOTAL)) is None


@pytest.mark.parametrize("entity_op", ["replace", "clear", None])
def test_u4_guard_every_other_op_stays_off(entity_op):
    assert _stamp(_verdict(entity_op), _focus(TOTAL)) is None


def test_u5_guard_replace_combine_with_no_customer_held_stays_off():
    """R8's `names_its_own_value`: the widening is for a held customer only."""
    assert _stamp(_verdict("replace_combine"), _focus({k: v for k, v in TOTAL.items() if k != "customer_ids"})) is None


def test_u6_a_ranking_held_for_a_customer_is_stamped():
    frame = {**TOTAL, "group_by": "product", "measure": "amount", "top_n": 5}
    held = _stamp(_verdict("reuse"), _focus(frame))
    assert held and held["customer_ids"] == [U1, U2], held
    assert "group_by" not in held and "top_n" not in held, held


@pytest.mark.parametrize(
    "frame",
    [
        {"group_by": "product", "date_from": "2026-10-01"},
        {**TOTAL, "group_by": "product", "stale": True},
        {**TOTAL, "group_by": "customer"},
    ],
    ids=["no-customer", "stale", "the-customer-is-the-ranked-side"],
)
def test_u7_guard_every_other_ranking_keeps_its_own_rules(frame):
    assert _stamp(_verdict("reuse"), _focus(frame)) is None


def test_u8_guard_a_held_customer_never_crosses_out_of_a_sales_answer():
    assert _stamp(_verdict("reuse"), _focus(TOTAL, domains=("order",))) is None
