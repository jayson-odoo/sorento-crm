"""SO-NUMBER-ASK, the SO LIST: "all my sales orders" / "my SOs" (owner option (2), PR #1435).

Owner rulings on the behaviour card (2 Oct 2026):

* Q1 (a) a period, the same as the DO ask: no period -> "Which period?" with This month /
  Last month; at most 31 days, rolling (`do_ask.MAX_DAYS`).
* Q2 (a) newest order date first, every status; a cancelled row carries the ❗ marker.
* Q3 (a) the company named once in the header, group name only, no count; when the links
  span two or more groups each row carries its group name.
* Q4 (a) gated by `sales_orders.outstanding`.

Seeded with crew's dev rows (sorento_cagent_stack, 2 Oct 2026): HANLIM's 17 SOs in Sep 2026
(the newest 15 as crew listed them, plus two more), cancelled SO418652, and a contact linked
to customers in several groups (crew's "Jayson", 437264483). `sales_orders.debtor_name` is
empty on dev, so the rows are seeded without one and the names come from the customer.

One real `engine.run_turn` per turn (the `test_customer_scope_lane.py` harness).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.chatbot.test_customer_scope_lane import ORDERS, _calls, _link_customers
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact
from tests.chatbot.test_so_number_ask import OUTSTANDING_KEY, SO_NOT_ENABLED, _seed_so

H1 = "HANLIM TRADING SDN BHD [A/C I]"
H3 = "HANLIM TRADING SDN BHD [A/C III]"
H4 = "HANLIM TRADING SDN BHD [A/C IV]"

#: Crew's rows, newest first (number, date, status, ledger), plus two older Sep SOs so the
#: month holds 17 as on dev. Lines give each its delivery word.
SEP_ROWS: list[tuple[str, str, str, str, list[tuple[int, int]]]] = [
    ("SO422095", "2026-09-21", "closed", H1, [(3, 3)]),
    ("SO422057", "2026-09-21", "open", H4, [(2, 0)]),
    ("SO422056", "2026-09-21", "closed", H3, [(5, 5)]),
    ("SO421624", "2026-09-15", "open", H1, [(15, 11), (11, 0)]),
    ("SO421478", "2026-09-15", "closed", H4, [(1, 1)]),
    ("SO421477", "2026-09-15", "closed", H3, [(1, 1)]),
    ("SO421157", "2026-09-14", "closed", H1, [(1, 1)]),
    ("SO421037", "2026-09-14", "open", H3, [(4, 0)]),
    ("SO420977", "2026-09-10", "closed", H1, [(1, 1)]),
    ("SO420631", "2026-09-09", "closed", H3, [(1, 1)]),
    ("SO420626", "2026-09-09", "closed", H1, [(1, 1)]),
    ("SO420420", "2026-09-08", "open", H1, [(6, 2)]),
    ("SO420050", "2026-09-07", "closed", H3, [(1, 1)]),
    ("SO419868", "2026-09-07", "closed", H1, [(1, 1)]),
    ("SO419633", "2026-09-03", "closed", H1, [(1, 1)]),
    ("SO419500", "2026-09-02", "closed", H4, [(1, 1)]),
    ("SO419400", "2026-09-01", "closed", H3, [(1, 1)]),
]

WORDS = {
    "SO422095": "Closed - fully delivered",
    "SO422057": "Open - not delivered yet",
    "SO422056": "Closed - fully delivered",
    "SO421624": "Open - partly delivered",
    "SO421037": "Open - not delivered yet",
    "SO420420": "Open - partly delivered",
}


def _date(iso: str) -> str:
    from datetime import date

    d = date.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def _seed_hanlim(session_factory) -> dict[str, str]:
    _seed_contact(session_factory, variables={})
    ids = dict(zip((H1, H3, H4), _link_customers(session_factory, H1, H3, H4)))
    for number, iso, status, ledger, lines in SEP_ROWS:
        _seed_so(session_factory, number, customer_id=ids[ledger], status=status, lines=lines,
                 debtor_name=None, order_date=iso)
    # Outside the month: the cancelled one crew found, and an October SO.
    _seed_so(session_factory, "SO418652", customer_id=ids[H1], status="cancelled", lines=[(2, 0)],
             debtor_name=None, order_date="2026-08-27")
    _seed_so(session_factory, "SO422500", customer_id=ids[H1], status="open", lines=[(1, 0)],
             debtor_name=None, order_date="2026-10-01")
    return ids


def _list_ask(start: str | None = None, end: str | None = None, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        domain_hint="order", intent_hint="check_order", order_status=None, entities=[],
        document=["SO"], self_reference=True, date_filter_start=start, date_filter_end=end,
    )
    base.update(over)
    return _parser_output(**base)


def _turn(session_factory, monkeypatch, qf, body="all my sales orders", attributes=(OUTSTANDING_KEY,)):
    result, captured = _run_turn(
        session_factory, monkeypatch, qf=qf, text_body=body,
        msg_id=f"ZZT-so-list-{uuid.uuid4().hex[:10]}", attributes=list(attributes),
        matches={}, mcp_response={"has_result": True, "response": "ZZT DO ROWS"},
    )
    return ((result.reply or {}).get("text") or ""), captured


class TestSoListForOneGroup:
    def test_september_lists_all_17_newest_first_with_one_header(self, session_factory, monkeypatch) -> None:
        """Q2 (a) + Q3 (a): every status, newest first, the group named once."""
        _seed_hanlim(session_factory)
        reply, captured = _turn(session_factory, monkeypatch, _list_ask("2026-09-01", "2026-09-30"))
        lines = reply.strip().split("\n")
        assert lines[0] == "Sales orders for HANLIM TRADING SDN BHD, 1 Sep 2026 to 30 Sep 2026:", reply
        assert [ln.split(" - ")[0] for ln in lines[1:]] == [r[0] for r in SEP_ROWS], reply
        for number, words in WORDS.items():
            iso = next(r[1] for r in SEP_ROWS if r[0] == number)
            assert f"{number} - {_date(iso)} - {words}" in lines, (number, reply)
        assert "[A/C" not in reply and "accounts" not in reply, reply
        assert "SO418652" not in reply and "SO422500" not in reply, reply
        assert _calls(captured, ORDERS) == [], captured

    def test_a_cancelled_row_carries_the_marker_and_no_delivery_word(self, session_factory, monkeypatch) -> None:
        """Q2 (a): 'SO418652 - 27 Aug 2026 - ❗ Cancelled'."""
        _seed_hanlim(session_factory)
        reply, _ = _turn(session_factory, monkeypatch, _list_ask("2026-08-10", "2026-09-02"), "my SOs")
        assert "SO418652 - 27 Aug 2026 - ❗ Cancelled" in reply.split("\n"), reply

    def test_an_empty_period_says_so_in_one_line(self, session_factory, monkeypatch) -> None:
        _seed_hanlim(session_factory)
        reply, _ = _turn(session_factory, monkeypatch, _list_ask("2026-07-01", "2026-07-31"))
        assert reply.strip() == "No sales orders for HANLIM TRADING SDN BHD from 1 Jul 2026 to 31 Jul 2026.", reply


class TestSoListPeriod:
    def test_no_period_asks_which_period_and_fetches_nothing(self, session_factory, monkeypatch) -> None:
        """Q1 (a): the DO ask's question, this month / last month as words to type."""
        _seed_hanlim(session_factory)
        reply, captured = _turn(session_factory, monkeypatch, _list_ask())
        assert reply.startswith("Which period for HANLIM TRADING SDN BHD?\n- This month ("), reply
        assert "- Last month (" in reply and "SO42" not in reply, reply
        assert captured == [], captured

    def test_the_typed_period_answers_the_question_and_runs_the_list(self, session_factory, monkeypatch) -> None:
        """The answer is an ordinary dated message; the SO ask and the links ride the focus."""
        _seed_hanlim(session_factory)
        _turn(session_factory, monkeypatch, _list_ask())
        reply, _ = _turn(
            session_factory, monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[],
                           date_filter_start="2026-09-01", date_filter_end="2026-09-30"),
            "september",
        )
        assert reply.startswith("Sales orders for HANLIM TRADING SDN BHD, 1 Sep 2026 to 30 Sep 2026:\nSO422095"), reply

    def test_more_than_31_days_is_refused_with_suggestions(self, session_factory, monkeypatch) -> None:
        """Q1 (a): the 31-day rolling cap."""
        _seed_hanlim(session_factory)
        reply, captured = _turn(session_factory, monkeypatch, _list_ask("2026-08-01", "2026-09-30"))
        assert reply.startswith("That is 2 months (01/08/2026 to 30/09/2026). I can show up to 31 days of sales orders at a time:"), reply
        assert "- Sep 2026" in reply and "- Aug 2026" in reply and "SO42" not in reply, reply
        assert captured == [], captured


class TestSoListMultiGroup:
    def test_rows_carry_their_group_when_the_links_span_groups(self, session_factory, monkeypatch) -> None:
        """Q3 (a), crew's multi-group contact: header names every group once; each row its own."""
        _seed_contact(session_factory, variables={})
        h1, soon, modern = _link_customers(
            session_factory, H1, "SOON HENG HARDWARE CO.SDN.BHD. [A/C I]", "MODERNMED SDN BHD",
        )
        _seed_so(session_factory, "SO422095", customer_id=h1, status="closed", lines=[(3, 3)], debtor_name=None, order_date="2026-09-21")
        _seed_so(session_factory, "SO421800", customer_id=soon, status="open", lines=[(1, 0)], debtor_name=None, order_date="2026-09-18")
        _seed_so(session_factory, "SO421700", customer_id=modern, status="cancelled", lines=[(1, 0)], debtor_name=None, order_date="2026-09-17")
        reply, _ = _turn(session_factory, monkeypatch, _list_ask("2026-09-01", "2026-09-30"))
        lines = reply.strip().split("\n")
        assert lines[0].startswith("Sales orders for HANLIM TRADING SDN BHD, SOON HENG HARDWARE CO.SDN.BHD., MODERNMED SDN BHD"), reply
        assert lines[1:] == [
            "SO422095 - 21 Sep 2026 - HANLIM TRADING SDN BHD - Closed - fully delivered",
            "SO421800 - 18 Sep 2026 - SOON HENG HARDWARE CO.SDN.BHD. - Open - not delivered yet",
            "SO421700 - 17 Sep 2026 - MODERNMED SDN BHD - ❗ Cancelled",
        ], reply


class TestSoListGateAndScope:
    def test_no_key_gets_the_not_enabled_line(self, session_factory, monkeypatch) -> None:
        """Q4 (a), before the period question."""
        _seed_hanlim(session_factory)
        reply, captured = _turn(session_factory, monkeypatch, _list_ask(), attributes=())
        assert reply.strip() == SO_NOT_ENABLED, reply
        assert captured == [], captured

    def test_another_customers_sos_never_appear(self, session_factory, monkeypatch) -> None:
        from tests.chatbot.test_customer_scope_lane import _other_customer

        _seed_hanlim(session_factory)
        foreign = _other_customer(session_factory, "ZZT FOREIGN SDN BHD")
        _seed_so(session_factory, "SO421999", customer_id=foreign, lines=[(1, 0)], debtor_name=None, order_date="2026-09-20")
        reply, _ = _turn(session_factory, monkeypatch, _list_ask("2026-09-01", "2026-09-30"))
        assert "SO421999" not in reply and "FOREIGN" not in reply, reply

    def test_outstanding_still_goes_to_the_outstanding_report(self, session_factory, monkeypatch) -> None:
        """The owner: the outstanding report is triggered only by "outstanding"."""
        _seed_hanlim(session_factory)
        _reply, captured = _turn(
            session_factory, monkeypatch, _list_ask(order_status="so_outstanding"), "my outstanding SOs",
        )
        assert [name for name, _ in captured] == ["crm_outstanding_report"], captured


class TestOwnersTwoTurnTranscriptIsDeterministic:
    """Tester on 99f7edb3: "status of SO422056" then "okay how about all my sales order?"
    gave the SO summary in 1 of 3 runs and a DO answer in the others: the parser does not
    reliably emit `document: ["SO"]` for that sentence. The engine decides from the words
    (`so_status.so_list_verdict`), so every parser reading below must give the SO list's
    period question, never a DO answer, the outstanding report or the old SO number."""

    TURN_2 = "okay how about all my sales order?"

    @pytest.mark.parametrize(
        "parsed",
        [
            {"document": ["SO"], "self_reference": True},
            {"document": None, "self_reference": True},
            {"document": [], "self_reference": True, "status": "outstanding"},
            {"document": ["DO"], "self_reference": True},
            {"document": None, "self_reference": False, "domain_hint": None},
        ],
        ids=["so_document", "no_document", "outstanding_status", "do_document", "no_domain"],
    )
    def test_all_my_sales_order_after_the_card_is_the_so_list(self, session_factory, monkeypatch, parsed) -> None:
        _seed_hanlim(session_factory)
        first, _ = _turn(
            session_factory, monkeypatch,
            _parser_output(
                domain_hint="order", intent_hint="check_order", order_status=None,
                entities=[{"raw": "SO422056", "hint": "order_number", "canonical_code": None,
                           "current_message": True, "confident": True}],
            ),
            "status of SO422056",
        )
        assert first.startswith("*SO422056*"), first
        verdict = dict(domain_hint="order", intent_hint="check_order", order_status=None, entities=[])
        verdict.update(parsed)
        reply, captured = _turn(session_factory, monkeypatch, _parser_output(**verdict), self.TURN_2)
        assert reply.startswith("Which period for HANLIM TRADING SDN BHD?\n- This month ("), reply
        assert "SO422056" not in reply and "Couldn't find" not in reply, reply
        assert captured == [], captured

    def test_lowercase_so_as_a_filler_word_is_not_an_so_ask(self, session_factory, monkeypatch) -> None:
        """'so' alone is ordinary English ("so what about my orders"): no SO list."""
        _seed_hanlim(session_factory)
        reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[],
                           self_reference=True),
            "so what about my orders",
        )
        assert not reply.startswith("Which period for") or "sales orders" not in reply, reply
        assert "Sales orders for" not in reply, reply

    def test_outstanding_in_the_words_keeps_the_outstanding_report(self, session_factory, monkeypatch) -> None:
        _seed_hanlim(session_factory)
        _reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[],
                           document=["SO"], status="outstanding", self_reference=True),
            "my outstsnding sales orders",
        )
        assert [name for name, _ in captured] == ["crm_outstanding_report"], captured


class TestOwnerHandTest3OctListAfterTheOutstandingSummary:
    """Owner hand test, 3 Oct 2026 (contact Jayson): after the SO outstanding summary
    ending "Reply 1 for the sales order list." (with its "Sales order list" button),
    "1" / the button / "give me the sales order list" re-ran the outstanding report and
    printed another summary, and "find all my sales order" printed the outstanding
    summary too. A customer-subject offer's sales order list IS the SO list, and an SO
    list ask over an open outstanding offer is the SO list."""

    REPORT = "crm_outstanding_report"

    def _summary_first(self, session_factory, monkeypatch) -> list[tuple[str, dict[str, Any]]]:
        from tests.chatbot.test_outstanding_lane import CUSTOMER_SUBJECT_HIT, _session_of

        _seed_hanlim(session_factory)
        result, captured = _run_turn(
            session_factory, monkeypatch,
            qf=_parser_output(
                domain_hint="order", intent_hint="check_order", order_status="so_outstanding", entities=[],
                self_reference=True, date_filter_start="2026-09-01", date_filter_end="2026-09-30",
            ),
            text_body="my outstanding sales orders in september",
            msg_id=f"ZZT-so-os-{uuid.uuid4().hex[:10]}", attributes=[OUTSTANDING_KEY], matches={},
            mcp_response=CUSTOMER_SUBJECT_HIT,
        )
        reply = (result.reply or {}).get("text") or ""
        assert [n for n, _ in captured] == [self.REPORT], captured
        assert "sales order list" in reply.casefold(), reply
        assert (_session_of(session_factory).get("open_question") or {}).get("kind") == "outstanding_detail"
        return captured

    @pytest.mark.parametrize(
        "body,parsed",
        [
            ("1", {"message_type": "casual", "intent_hint": None, "domain_hint": None, "reference_positions": [1]}),
            ("Sales order list", {"message_type": "casual", "intent_hint": None, "domain_hint": None, "reference_positions": [1]}),
            ("give me the sales order list", {"domain_hint": "order", "intent_hint": "check_order", "reference_positions": [1]}),
            ("give me the sales order list", {"domain_hint": "order", "intent_hint": "check_order", "document": ["SO"]}),
        ],
        ids=["reply_1", "button", "words_as_pick", "words_as_so_ask"],
    )
    def test_the_list_follow_up_is_the_so_list_for_the_reports_window(self, session_factory, monkeypatch, body, parsed) -> None:
        self._summary_first(session_factory, monkeypatch)
        verdict = dict(order_status=None, entities=[])
        verdict.update(parsed)
        reply, captured = _turn(session_factory, monkeypatch, _parser_output(**verdict), body)
        assert reply.startswith("Sales orders for HANLIM TRADING SDN BHD, 1 Sep 2026 to 30 Sep 2026:\nSO422095"), reply
        assert self.REPORT not in [n for n, _ in captured], captured

    @pytest.mark.parametrize("status", [None, "outstanding"])
    def test_find_all_my_sales_order_over_the_open_summary_is_the_so_list(self, session_factory, monkeypatch, status) -> None:
        self._summary_first(session_factory, monkeypatch)
        reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[],
                           document=["SO"], status=status, self_reference=True),
            "find all my sales order",
        )
        assert reply.startswith(("Sales orders for HANLIM TRADING SDN BHD", "Which period for HANLIM TRADING SDN BHD?")), reply
        assert self.REPORT not in [n for n, _ in captured], captured
