"""SO-NUMBER-ASK: an ask about one SO number answers about that SO only.

Tester note on PR #1433 ("E3 SO number"): a linked dealer asked `status of SO422056`. The
resolver has no probe for `sales_orders.so_number` (it reads `orders.order_number`, the DO
book), so the token came back unresolved. The engine then swapped the resolver's
not-found exit for the dealer's linked customers (`engine._scoped_compatible` +
`engine._pass_scope_gate`), the orders list ran on those customer ids alone, and the
reply was a 20-row DO dump over every linked customer closed by "I could not find
SO422056." `turn_runtime._answered_unfiltered` did not catch it because the scope rows
carry real uuids, so the fetch did not read as unfiltered.

Rule under test: a turn whose only typed subject is a word nobody could place is a miss,
whatever customer scope the contact carries. The read on the scope alone may still go out
(it is the contact's own data), but its rows never reach the reply: the reply is the one
miss line production composes for any unplaced word, with no scope header above it.

Same harness as `test_customer_scope_lane.py` (one real `engine.run_turn`, parser,
access, resolver and MCP faked). Postgres only.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from tests.chatbot.test_customer_scope_lane import ORDERS, _calls, _link_customers
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact

SO = "SO422056"
DUMP_DO = "DOZZTDUMP1"

#: What the orders list would have answered on the scope alone: a DO the SO ask never named.
DO_DUMP = {
    "has_result": True,
    "response": f"*Orders*\n1. {DUMP_DO} - ZZT OWN A - Delivered\n2. DOZZTDUMP2 - ZZT OWN B - Processing",
    "items": [{"order_number": DUMP_DO}, {"order_number": "DOZZTDUMP2"}],
}


def _so_ask(hint: str) -> dict[str, Any]:
    return _parser_output(
        domain_hint="order",
        intent_hint="check_order",
        order_status=None,
        entities=[{"raw": SO, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}],
    )


def _turn(session_factory, monkeypatch, qf: dict[str, Any], body: str):
    result, captured = _run_turn(
        session_factory,
        monkeypatch,
        qf=qf,
        text_body=body,
        msg_id=f"ZZT-so-ask-{uuid.uuid4().hex[:10]}",
        attributes=[],
        matches={},  # the resolver places nothing: no SO probe exists
        mcp_response=DO_DUMP,
    )
    return ((result.reply or {}).get("text") or ""), captured


class TestUnresolvedSoNumberIsOneMissLine:
    @pytest.mark.parametrize("hint", ["order", "order_number", "customer_order"])
    def test_linked_dealer_gets_no_do_dump(self, session_factory, monkeypatch, hint) -> None:
        _seed_contact(session_factory, variables={})
        _link_customers(session_factory, "ZZT OWN A", "ZZT OWN B")

        reply, captured = _turn(session_factory, monkeypatch, _so_ask(hint), f"status of {SO}")

        assert DUMP_DO not in reply, reply
        assert "ZZT OWN" not in reply, reply
        assert "Customer:" not in reply, reply
        assert reply.startswith(f'Couldn\'t find: "{SO}"'), reply

    def test_bare_order_ask_still_runs_on_the_links(self, session_factory, monkeypatch) -> None:
        """Guard: the fix is about a typed number that did not resolve. An order ask naming
        nothing at all still runs on the links (AC-CS-30)."""
        _seed_contact(session_factory, variables={})
        own = _link_customers(session_factory, "ZZT OWN A", "ZZT OWN B")

        _reply, captured = _turn(
            session_factory,
            monkeypatch,
            _parser_output(domain_hint="order", intent_hint="check_order", order_status=None, entities=[]),
            "my orders",
        )

        (args,) = _calls(captured, ORDERS)
        assert sorted(args["customer_ids"]) == sorted(own), args
