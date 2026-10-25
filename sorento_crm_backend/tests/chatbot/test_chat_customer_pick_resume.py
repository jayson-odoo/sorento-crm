"""CHAT-CUSTOMER-PICK-RESUME (owner 25 Oct ~17:00; PLAN-chat-customer-pick-resume-1025.md): the answer to a customer
picker over a held sales report resumes THAT ask with the picked customer, whatever axis fields the parser adds to a
pure pick turn.

Prod 25 Oct 10:02, prompt v63: t1 "Dealer <customer> oct total sales" -> "Which one do you mean? 1. ... 2. ...";
t2 "1" -> "I can't break sales down by customer yet. I can show them by month, by year or by channel." The t2 parse:
`business_query`, `order_status` sales_analysis, `group_by` "customer", `sales_channel` null, `entity_op` reuse,
`open_question_answer {mode pick, picked [1]}`. Expected: the October Dealer total for option 1.

Engine harness: `test_new_ask_drops_sales_channel.chat` (real `engine.run_turn`, Postgres, parser / access /
resolver / MCP faked). Fake customers only (public repo).
"""
from __future__ import annotations

from typing import Any

from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_new_ask_drops_sales_channel import (  # noqa: F401  (fixture)
    CUSTOMER_UUID_1, CUSTOMER_UUID_2, _ambiguous_customer_services, _report_calls, _reply, chat,
)
from tests.chatbot.test_sales_analysis_company_pick import ANALYSIS, _calls, _pick

REFUSAL = "I can't break sales down by"
OCT_2026 = {"date_mode": "month", "date_filter_start": "2026-10-01", "date_filter_end": "2026-10-31"}


def _t1(order_status: str = "sales_report") -> dict[str, Any]:
    """"Dealer <customer> oct total sales": one customer word matching two accounts."""
    return _parser_output(
        message_type="business_query", domain_hint="sales", intent_hint="check_order", order_status=order_status,
        sales_channel="dealer", domain_in_message=True, entity_op="replace_combine",
        entities=[{"raw": "zz demo", "hint": "customer", "canonical_code": None,
                   "current_message": True, "confident": True}],
        **OCT_2026,
    )


def _t2(**over: Any) -> dict[str, Any]:
    """"1", field for field as prod v63 parsed it: a pick that also names an axis."""
    base: dict[str, Any] = dict(
        message_type="business_query", domain_hint="sales", intent_hint="check_order",
        order_status="sales_analysis", group_by="customer", sales_channel=None, entities=[],
        entity_op="reuse", domain_in_message=False, open_question_answer=_pick(1),
    )
    return _parser_output(**{**base, **over})


def _ask_then_pick(chat, tag: str, t1: dict[str, Any] | None = None, t2: dict[str, Any] | None = None,
                   text: str = "1"):
    _r1, captured1 = chat(t1 or _t1(), "Dealer zz demo oct total sales", f"ZZT-cpr-{tag}-1",
                          resolve_services=_ambiguous_customer_services())
    assert _report_calls(captured1) == [], captured1
    assert (chat.session().get("open_question") or {}).get("kind") == "customer_pick", (
        "setup: the customer picker must be armed", chat.session().get("open_question"),
    )
    return chat(t2 or _t2(), text, f"ZZT-cpr-{tag}-2")


def _assert_resumed(result: Any, captured: list[tuple[str, dict[str, Any]]], uuid: str = CUSTOMER_UUID_1) -> None:
    assert REFUSAL not in _reply(result), _reply(result)
    assert _calls(captured, ANALYSIS) == [], f"the pick never runs the company analysis: {captured}"
    calls = _report_calls(captured)
    assert len(calls) == 1, captured
    args = calls[0]
    assert args.get("customer_ids") == [uuid], args
    assert args.get("channel") == "dealer", args
    assert args.get("date_from") == "2026-10-01" and args.get("date_to") == "2026-10-31", args
    assert not args.get("group_by"), args


def test_p1_the_prod_pick_with_group_by_customer_resumes_the_held_report(chat):
    result, captured = _ask_then_pick(chat, "p1")
    _assert_resumed(result, captured)


def test_p2_a_pick_with_status_sales_report_and_group_by_customer_too(chat):
    result, captured = _ask_then_pick(chat, "p2", t2=_t2(order_status="sales_report"))
    _assert_resumed(result, captured)


def test_g2_guard_a_pick_with_another_axis_month_is_today_s_report(chat):
    """Not this rule (month is no roster kind, `without_pick_axis` leaves it): green before the fix too."""
    result, captured = _ask_then_pick(chat, "g2", t2=_t2(group_by="month"))
    _assert_resumed(result, captured)


def test_p4_the_second_option_picks_the_second_account(chat):
    result, captured = _ask_then_pick(chat, "p4", t2=_t2(open_question_answer=_pick(2)), text="2")
    _assert_resumed(result, captured, CUSTOMER_UUID_2)


def test_g1_guard_the_plain_pick_parse_still_resumes(chat):
    """The pick parse with no axis (today's green path) is unchanged."""
    result, captured = _ask_then_pick(chat, "g1", t2=_t2(group_by=None, order_status=None))
    _assert_resumed(result, captured)




# ------------------------------------------------ the seam, unit level (`report_ask.without_pick_axis`)

import pytest  # noqa: E402

from app.services.chatbot.lanes.business import report_ask  # noqa: E402
from app.services.chatbot.turn.pending import ask as pending_ask  # noqa: E402


def _open(kind: str):
    return pending_ask(kind, [{"position": 1, "label": "A"}, {"position": 2, "label": "B"}], team=None, asked_at_turn=1)


@pytest.mark.parametrize(("kind", "axis"), [("customer_pick", "customer"), ("product_pick", "product")])
def test_u1_a_pick_whose_axis_is_the_roster_kind_drops_it(kind: str, axis: str) -> None:
    out = report_ask.without_pick_axis({"group_by": axis, "open_question_answer": _pick(1)}, _open(kind))
    assert out["group_by"] is None, out


def test_u2_a_bare_position_pick_drops_it_too() -> None:
    out = report_ask.without_pick_axis({"group_by": "Customer", "reference_positions": [2]}, _open("customer_pick"))
    assert out["group_by"] is None, out


@pytest.mark.parametrize(
    ("verdict", "kind"),
    [
        ({"group_by": "month", "open_question_answer": _pick(1)}, "customer_pick"),  # another axis is the message's own
        ({"group_by": "customer", "open_question_answer": {"mode": "all", "picked": []}}, "customer_pick"),  # "all"
        ({"group_by": "customer", "open_question_answer": {"mode": None, "picked": []}}, "customer_pick"),  # no pick
        ({"group_by": "customer", "open_question_answer": _pick(1)}, "tier_pick"),  # another roster
        ({"group_by": "product", "open_question_answer": _pick(1)}, "customer_pick"),  # not the roster's kind
    ],
)
def test_u3_guards_leave_the_verdict_untouched(verdict: dict[str, Any], kind: str) -> None:
    assert report_ask.without_pick_axis(verdict, _open(kind)) is verdict


def test_u4_no_open_question_is_untouched() -> None:
    verdict = {"group_by": "customer", "open_question_answer": _pick(1)}
    assert report_ask.without_pick_axis(verdict, None) is verdict


# ------------------------------------------------ owner add-on: a "picker" of one customer never asks

from app.services.chatbot.lanes.business.resolve_gate import name_unnamed_customers  # noqa: E402
from app.services.chatbot.lanes.business.services import ResolveGateServices  # noqa: E402
from tests.chatbot.conftest import validating_resolve_entity  # noqa: E402

ONE_NAME = "ZZ DEMO SANITARYWARE SDN BHD"


def _named_and_unnamed(uuid_a: str, uuid_b: str) -> ResolveGateServices:
    """Owner console 25 Oct: one customer word, two ledgers of ONE customer, the second matched with no name."""

    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["zz demo"],
            "resolutions": [{"token": "zz demo", "matches": [
                {"entity_type": "customer", "canonical_code": "300-ZZ008", "uuid": uuid_a, "company_code": "SRT",
                 "display": {"customer_name": ONE_NAME}},
                {"entity_type": "customer", "canonical_code": "300-ZZ009", "uuid": uuid_b, "company_code": "SRT",
                 "display": {}},
            ]}],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve),
        probe=lambda **_: {"items": [], "has_result": False},
    )


def test_o1_one_customer_behind_a_named_and_an_unnamed_match_is_not_asked(chat, session_factory):
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import customer

    db = session_factory()
    ids = [customer(db, company_id=DEFAULT_COMPANY_ID, name=ONE_NAME).id for _ in range(2)]
    db.commit()
    db.close()
    result, captured = chat(_t1(), "Dealer zz demo oct total sales", "ZZT-cpr-o1-1",
                            resolve_services=_named_and_unnamed(*ids))
    assert "Which one do you mean" not in _reply(result), _reply(result)
    assert (chat.session().get("open_question") or {}).get("kind") != "customer_pick", chat.session().get("open_question")
    calls = _report_calls(captured)
    assert len(calls) == 1 and sorted(calls[0].get("customer_ids") or []) == sorted(ids), captured
    assert calls[0].get("channel") == "dealer", calls[0]
    assert calls[0].get("date_from") == "2026-10-01" and calls[0].get("date_to") == "2026-10-31", calls[0]


def test_u5_only_an_unnamed_customer_match_takes_the_crm_name() -> None:
    resolved = {
        "resolutions": [{"token": "zz", "matches": [
            {"entity_type": "customer", "uuid": "a", "display": {"customer_name": "KEPT"}},
            {"entity_type": "customer", "uuid": "b", "display": {}},
            {"entity_type": "customer", "uuid": "c", "display": {"debtor_name": "DEBTOR"}},
            {"entity_type": "product", "uuid": "d", "display": {}},
        ]}],
        "intersection": [{"entity_type": "customer", "uuid": "e"}],
    }
    asked: list[list[str]] = []

    def names(ids: list[str]) -> dict[str, str]:
        asked.append(ids)
        return {i: f"CRM {i}" for i in ids}

    name_unnamed_customers(resolved, names)
    matches = resolved["resolutions"][0]["matches"]
    assert asked == [["b", "e"]], asked
    assert [m["display"].get("customer_name") for m in matches] == ["KEPT", "CRM b", None, None], matches
    assert resolved["intersection"][0]["display"] == {"customer_name": "CRM e"}, resolved


def _grouped_pair(uuid_a: str, uuid_b: str) -> ResolveGateServices:
    """The prod console shapes (crew, 25 Oct): a debtor-name hit on the "[A/C I]" ledger and a customer hit on the
    "(PROJECT)" ledger, both ledgers in ONE customer group."""

    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["zz demo"],
            "resolutions": [{"token": "zz demo", "matches": [
                {"entity_type": "customer", "canonical_code": ONE_NAME, "uuid": uuid_a, "company_code": "SRT",
                 "display": {"debtor_name": ONE_NAME, "debtor_code": "300-ZZ004", "source": "orders",
                             "customer_name": f"{ONE_NAME} [A/C I]"}},
                {"entity_type": "customer", "canonical_code": f"{ONE_NAME} (PROJECT)", "uuid": uuid_b,
                 "company_code": "SRT", "display": {"customer_name": f"{ONE_NAME} (PROJECT)"}},
            ]}],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve),
        probe=lambda **_: {"items": [], "has_result": False},
    )


def test_o2_two_ledgers_of_one_customer_group_are_one_customer_not_a_picker(chat, session_factory):
    from app.models.order import CustomerGroup
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._mc_lookup_seed import customer

    db = session_factory()
    group = CustomerGroup(name=ONE_NAME, company_id=DEFAULT_COMPANY_ID)
    db.add(group)
    db.flush()
    rows = [customer(db, company_id=DEFAULT_COMPANY_ID, name=f"{ONE_NAME} {marker}") for marker in ("[A/C I]", "(PROJECT)")]
    for row in rows:
        row.customer_group_id = group.id
    ids = [row.id for row in rows]
    db.commit()
    db.close()
    result, captured = chat(_t1(), "Dealer zz demo oct total sales", "ZZT-cpr-o2-1",
                            resolve_services=_grouped_pair(*ids))
    assert "Which one do you mean" not in _reply(result), _reply(result)
    calls = _report_calls(captured)
    assert len(calls) == 1 and sorted(calls[0].get("customer_ids") or []) == sorted(ids), captured
    assert calls[0].get("channel") == "dealer", calls[0]
