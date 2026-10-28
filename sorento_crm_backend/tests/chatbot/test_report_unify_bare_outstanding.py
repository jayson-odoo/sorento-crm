"""REPORT-UNIFY phase 3 fix round, R4: a bare "outstanding" (no filter, no axis, no document word) asks the kind
(`KIND_QUESTION`), then runs the whole company figure for that kind. It is never the order list."""
from __future__ import annotations

import pytest

from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (bot / console are fixtures)
    KIND_QUESTION,
    NO_DATES,
    _only_report_ask,
    _reply,
    _status,
    bot,
    console,
)


@pytest.mark.parametrize("status", ["outstanding", "outstanding_both"])
def test_r4_a_bare_outstanding_asks_the_kind_and_runs_nothing(bot, status) -> None:
    text, calls = bot.say(_status(status, basis=None, **NO_DATES), "outstanding")
    assert calls == [], calls
    assert KIND_QUESTION in text, text


def test_r4_the_kind_answer_runs_the_whole_company_figure_never_the_order_list(bot) -> None:
    bot.say(_status("outstanding", basis=None, **NO_DATES), "outstanding")
    text, calls = bot.say(
        _reply(
            message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis="pending_delivery",
            open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
        ),
        "pending delivery",
    )
    args = _only_report_ask(calls)
    assert args["basis"] == "pending_delivery", args
    assert not args.get("customer_ids") and not args.get("product_code") and not args.get("group_by"), args
    assert "date_from" not in args and "date_to" not in args, args


def test_r4_an_outstanding_with_a_document_word_is_still_the_order_list(bot) -> None:
    """The document list asks (an SO / DO list) are not this rule: `document` names the list."""
    text, calls = bot.say(_status("outstanding", basis=None, document=["SO"], **NO_DATES), "outstanding sales orders list")
    assert all(n != "crm_report_ask" for n, _a in calls), calls


def test_s5_a_ranking_with_a_named_outstanding_kind_still_asks_the_measure(bot) -> None:
    """Phase 3 S5: only a total (and a month trend) shows both measures without asking; a ranking by an axis names what it
    ranks by, even on an outstanding kind."""
    text, calls = bot.say(
        _status("outstanding", group_by="customer", top_n=5, measure=None, basis="pending_delivery", **NO_DATES),
        "top 5 customers pending delivery",
    )
    assert calls == [], calls
    assert "By quantity or by amount?" in text, text


def test_s11_a_kind_answer_after_the_outstanding_reveal_was_revoked_is_refused(bot, monkeypatch) -> None:
    """S11: the reveal is re-read on the answering turn, not carried from the asking turn."""
    from app.services.chatbot import engine as engine_mod

    bot.say(_status("outstanding", basis=None, **NO_DATES), "outstanding")
    monkeypatch.setattr(
        engine_mod,
        "check_access",
        lambda db, *, agent_code, contact_id, space_id: {
            "allowed": True, "decision": "allow", "agent_name": "General",
            "attributes": ["sales_orders.sales_report"], "all_attributes_allowed": None,
        },
    )
    text, calls = bot.say(
        _reply(
            message_type="business_query", domain_hint=None, intent_hint=None, entities=[], basis="pending_delivery",
            open_question_answer={"mode": "fill", "picked": [], "items": [], "qty_for_all": None},
        ),
        "pending delivery",
    )
    assert calls == [], calls
    assert text.strip() == "Outstanding is not enabled for your account.", text
