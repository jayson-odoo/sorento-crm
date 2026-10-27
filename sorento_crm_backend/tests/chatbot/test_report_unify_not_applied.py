"""REPORT-UNIFY plan 2.4 (P11): a parsed filter with no route param prints a Not applied line."""
from __future__ import annotations

from tests.chatbot.test_report_unify_routing import (  # noqa: F401  (console, bot are fixtures)
    NO_DATES,
    _customer,
    _e,
    _only_report_ask,
    _status,
    bot,
    console,
)


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("Not applied:")]


def test_p11_an_account_number_on_an_ask_with_no_customer_filter_is_said_not_applied() -> None:
    from app.services.chatbot.lanes.business import report_ask

    verdict = {"entities": [{**_e("dealer", "channel"), "account": 3}]}
    assert report_ask.unapplied_words(verdict, {"group_by": "customer"}) == [
        "a/c 3 (no account filter)"
    ]
    # The same account on a customer the ask did narrow to is the gate's own narrowing, applied.
    assert report_ask.unapplied_words(verdict, {"customer_ids": ["c1"]}) == ["dealer (no channel filter)"]


def test_p11_a_kind_the_report_does_not_filter_by_prints_a_not_applied_line(bot) -> None:
    text, calls = bot.say(
        _status("outstanding", _customer(bot), _e("TRP-9", "transporter"), basis="unpaid", **NO_DATES),
        "unpaid invoices for zzt rank customer by TRP-9",
    )
    _only_report_ask(calls)
    lines = _lines(text)
    assert len(lines) == 1 and "TRP-9" in lines[0], text


def test_p11_an_ask_whose_every_filter_applies_prints_no_not_applied_line(bot) -> None:
    text, calls = bot.say(
        _status("outstanding", _customer(bot), basis="unpaid", **NO_DATES), "unpaid invoices for zzt rank customer"
    )
    _only_report_ask(calls)
    assert not _lines(text), text


def test_p11_a_parsed_filter_with_no_route_param_that_is_the_only_subject_asks_instead_of_answering() -> None:
    """AC-RU-14 second half: nothing the ask names can be applied (and nothing is grouped), so the figure is not
    what was asked: the question names the words."""
    from app.services.chatbot.lanes.business import report_ask

    words = ["TRP-9 (no transporter filter)"]
    question = report_ask.sole_unapplied_question(
        words, {"basis": "delivered", "sort": "desc", "date_from": "2026-09-01", "date_to": "2026-09-30"}
    )
    assert question and "TRP-9" in question and question.endswith("?"), question
    # a grouped ask, or one with an applied filter, is answered (with the Not applied line)
    assert report_ask.sole_unapplied_question(words, {"basis": "delivered", "group_by": "customer"}) is None
    assert report_ask.sole_unapplied_question(words, {"basis": "delivered", "customer_ids": ["c1"]}) is None
    assert report_ask.sole_unapplied_question([], {"basis": "delivered"}) is None
