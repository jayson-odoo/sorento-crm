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
to customers in several groups (crew's "CONTACT B", 900000008). `sales_orders.debtor_name` is
empty on dev, so the rows are seeded without one and the names come from the customer.

One real `engine.run_turn` per turn (the `test_customer_scope_lane.py` harness).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.chatbot.test_customer_scope_lane import ORDERS, SALES_KEY, _calls, _link_customers
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
        """The owner: the outstanding report is triggered only by "outstanding". REPORT-UNIFY: that is the report ask
        now, its kind (undelivered orders) named by the sales order outstanding status."""
        _seed_hanlim(session_factory)
        _reply, captured = _turn(
            session_factory, monkeypatch, _list_ask(order_status="so_outstanding"), "my outstanding SOs",
            attributes=(OUTSTANDING_KEY, SALES_KEY),
        )
        assert [name for name, _ in captured] == ["crm_report_ask"], captured
        assert captured[0][1]["basis"] == "outstanding", captured


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
        """REPORT-UNIFY: "outstanding" is the report ask; the sales order words give its kind (undelivered orders)."""
        _seed_hanlim(session_factory)
        reply, captured = _turn(
            session_factory, monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[],
                           document=["SO"], status="outstanding", self_reference=True),
            "my outstsnding sales orders", attributes=(OUTSTANDING_KEY, SALES_KEY),
        )
        assert [n for n, _ in captured] == ["crm_report_ask"] and captured[0][1]["basis"] == "outstanding", (reply, captured)


def _live(**over: Any) -> dict[str, Any]:
    """The live parser's reading (gpt-5.4-mini, cloud pass on PR #1435, 3 Oct 2026): it
    carries `so_outstanding` and the SO document off the conversation onto a message whose
    words name neither ("1", "september")."""
    base: dict[str, Any] = dict(
        message_type="business_query", domain_hint="order", intent_hint="check_order",
        order_status="so_outstanding", document=["SO"], self_reference=True, entities=[],
        entity_op="reuse",
    )
    base.update(over)
    return _parser_output(**base)


_PICK_1 = dict(reference_positions=[1], reference_target="result",
               open_question_answer={"mode": "pick", "items": [], "picked": [1], "qty_for_all": None})


class TestCloudPassLiveParserReadings:
    """Cloud pass on PR #1435 with the LIVE parser, 3 of 3 runs each: "1" under the
    outstanding summary printed the summary again (the stale `document: ["SO"]` read as a
    named document, a new ask for the report), and "september" after the SO list's period
    question printed the outstanding report (the stale `so_outstanding` kept the list from
    running). The words decide: neither message says "outstanding" or names a document."""

    def _summary(self, session_factory, monkeypatch, body: str, **over: Any) -> None:
        from tests.chatbot.test_outstanding_lane import CUSTOMER_SUBJECT_HIT

        result, captured = _run_turn(
            session_factory, monkeypatch, qf=_live(**over), text_body=body,
            msg_id=f"ZZT-so-live-{uuid.uuid4().hex[:10]}", attributes=[OUTSTANDING_KEY], matches={},
            mcp_response=CUSTOMER_SUBJECT_HIT,
        )
        assert [n for n, _ in captured] == ["crm_outstanding_report"], captured
        assert "Reply 1 for the sales order list." in ((result.reply or {}).get("text") or "")

    def test_all_my_sales_orders_then_september_is_the_so_list(self, session_factory, monkeypatch) -> None:
        _seed_hanlim(session_factory)
        asked, _ = _turn(session_factory, monkeypatch, _live(order_status="sales_report", status="sales_report"),
                         "all my sales orders")
        assert asked.startswith("Which period for HANLIM TRADING SDN BHD?"), asked
        reply, captured = _turn(
            session_factory, monkeypatch, _live(date_filter_start="2026-09-01", date_filter_end="2026-09-30"),
            "september",
        )
        assert reply.startswith("Sales orders for HANLIM TRADING SDN BHD, 1 Sep 2026 to 30 Sep 2026:\nSO422095"), reply
        assert "crm_outstanding_report" not in [n for n, _ in captured], captured

    def test_outstanding_typed_after_the_list_still_runs_the_report(self, session_factory, monkeypatch) -> None:
        """Guard: the word "outstanding" keeps the report, on the SO list too (now the report ask)."""
        _seed_hanlim(session_factory)
        _turn(session_factory, monkeypatch, _live(order_status="sales_report", status="sales_report"),
              "all my sales orders")
        reply, captured = _turn(
            session_factory, monkeypatch,
            _live(date_filter_start="2026-09-01", date_filter_end="2026-09-30"),
            "my outstanding sales orders in september", attributes=(OUTSTANDING_KEY, SALES_KEY),
        )
        assert [n for n, _ in captured] == ["crm_report_ask"] and captured[0][1]["basis"] == "outstanding", (reply, captured)


class TestCloudPassParserDropsTheTypedWords:
    """Cloud pass on PR #1435, live parser: "september" answering the SO list's "Which
    period?" came back with no dates in 2 of 3 runs, and "my outstanding sales orders in
    september" with no status or no dates in 2 of 9. The words decide."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("september", ("2026-09-01", "2026-09-30")),
            ("Sep", ("2026-09-01", "2026-09-30")),
            ("november", ("2025-11-01", "2025-11-30")),
            ("feb 2026", ("2026-02-01", "2026-02-28")),
            ("last month", ("2026-09-01", "2026-09-30")),
            ("this month", ("2026-10-01", "2026-10-31")),
            ("may I see my SOs", None),
            ("15 Sep to 10 Oct", None),
            ("august and september", None),
            ("all my sales orders", None),
        ],
    )
    def test_typed_month(self, text, expected) -> None:
        from datetime import date

        from app.services.chatbot.so_status import typed_month

        got = typed_month(text, date(2026, 10, 3))
        assert (None if got is None else (got[0].isoformat(), got[1].isoformat())) == expected

    def test_all_my_sales_orders_then_september_without_dates(self, session_factory, monkeypatch) -> None:
        _seed_hanlim(session_factory)
        asked, _ = _turn(session_factory, monkeypatch, _live(order_status=None), "all my sales orders")
        assert asked.startswith("Which period for HANLIM TRADING SDN BHD?"), asked
        monkeypatch.setattr("app.services.chatbot.do_ask.today_myt", lambda: __import__("datetime").date(2026, 10, 3))
        reply, captured = _turn(
            session_factory, monkeypatch, _live(order_status="sales_report", status="sales_report"), "september"
        )
        assert reply.startswith("Sales orders for HANLIM TRADING SDN BHD, 1 Sep 2026 to 30 Sep 2026:\nSO422095"), reply
        assert captured == [], captured

    def test_outstanding_in_september_without_a_status_is_the_report(self, session_factory, monkeypatch) -> None:
        """The words give the status back; it is the report ask, its kind the sales order status's (REPORT-UNIFY)."""
        _seed_hanlim(session_factory)
        result, captured = _run_turn(
            session_factory, monkeypatch,
            qf=_live(order_status=None, self_reference=False),
            text_body="my outstanding sales orders in september",
            msg_id=f"ZZT-so-live-{uuid.uuid4().hex[:10]}", attributes=[OUTSTANDING_KEY, SALES_KEY], matches={},
            mcp_response={"has_result": False},
        )
        assert [n for n, _ in captured] == ["crm_report_ask"] and captured[0][1]["basis"] == "outstanding", captured


class TestReviewRoundCarriedStatusGuards:
    """Reviewer on the cloud-pass round: `period_on_so_list` must answer a PERIOD only, a
    lower-case "so" next to a quantity is no SO number, and a pick the parser marked by
    mode alone still answers the offer."""

    def _on_the_list(self, session_factory, monkeypatch) -> None:
        _seed_hanlim(session_factory)
        reply, _ = _turn(session_factory, monkeypatch, _live(order_status=None, date_filter_start="2026-09-01",
                                                          date_filter_end="2026-09-30"), "all my sales orders")
        assert reply.startswith("Sales orders for HANLIM TRADING SDN BHD, 1 Sep 2026"), reply

    def test_pending_delivery_after_the_list_is_not_the_list(self, session_factory, monkeypatch) -> None:
        self._on_the_list(session_factory, monkeypatch)
        reply, _ = _turn(session_factory, monkeypatch, _live(order_status="do_outstanding", document=["SO"]),
                         "which ones are still pending delivery?")
        assert not reply.startswith("Sales orders for"), reply

    def test_how_much_did_i_buy_after_the_list_is_not_the_list(self, session_factory, monkeypatch) -> None:
        self._on_the_list(session_factory, monkeypatch)
        reply, _ = _turn(session_factory, monkeypatch,
                         _live(order_status="sales_report", status="sales_report", date_filter_start="2026-09-01",
                               date_filter_end="2026-09-30"),
                         "how much did I buy in september")
        assert not reply.startswith("Sales orders for"), reply

    @pytest.mark.parametrize("text", ["price 1500 so 1500 pcs ok", "ok so 2026 how much did I buy"])
    def test_lower_case_so_next_to_a_number_is_no_so_number(self, text) -> None:
        from app.services.chatbot.so_status import typed_so_numbers_verdict

        verdict = {"entities": [{"raw": "SRTWC8517", "hint": "product", "current_message": True}]}
        assert typed_so_numbers_verdict(verdict, text) == (verdict, None)

    def test_typed_number_keeps_no_identity_of_the_copied_one(self) -> None:
        from app.services.chatbot.so_status import typed_so_numbers_verdict

        verdict = {"entities": [{"raw": "SO422056", "hint": "order", "canonical_code": "SO422056", "uuid": "abc",
                                 "current_message": True}]}
        fixed, rule = typed_so_numbers_verdict(verdict, "status of SO421624")
        assert rule == "typed_so_numbers"
        assert fixed["entities"] == [{"raw": "SO421624", "hint": "order", "canonical_code": None,
                                      "current_message": True, "confident": True}]

    @pytest.mark.parametrize("text", ["order 5000 pcs in march", "SO 4216 september"])
    def test_a_quantity_is_not_a_year(self, text) -> None:
        from datetime import date

        from app.services.chatbot.so_status import typed_month

        got = typed_month(text, date(2026, 10, 3))
        assert got is not None and got[0].year in (2025, 2026), got
