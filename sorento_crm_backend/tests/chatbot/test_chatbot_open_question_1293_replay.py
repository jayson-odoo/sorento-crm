"""Issue #1293, W4: the owner's 26 Sep 2026 console sessions on contact 437264483,
replayed through `engine.run_turn`.

Only the PARSER is stubbed, and each turn's stub is what the parser should answer under
the new contract (the open question object in, `open_question_answer` out). Everything
else is the real code: the real resolver over seeded product rows (it reproduces the
owner's own did-you-mean lists, "Couldn't find STWC2867. Did you mean: 1. SRTWC286-SH 2.
SRTWC286-SH-P"), `apply`, the lanes, the session written to `respond_contacts` and read
back next turn, and the stock tool's reply rendered by the real MCP presenter
(`sorento_crm_mcp.presenters.present_response`) from an availability-mode payload in
which every stated quantity is more than the dealer may be told about (R6 B1, "too big").

The sessions (PR #1247's comments quote each verbatim):
* 07:18Z, the round 3 hand test: "check stock srtwc286", "1", "10", "2", "3".
* 08:18Z, the round 4 console test: "all", "1. 10, 2. 5", "10", "tia" (tiga).
* 10:11Z, the round 7 console test: rows 1 to 12, and the answer to row 12's question.
* 14:06Z, the round 8 console test: the did-you-mean and "the first one, I need 2".
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot import turn_runtime

from tests.chatbot._turn_helpers import entity
from tests.chatbot.test_chatbot_open_question_1293 import answer, item
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_rearch_s3_attribute_first import SORENTO, _link_contact_company
from tests.chatbot.test_rearch_s3_roster_from_resolver import _seed_contact, _seed_products

TOO_BIG = "the quantity is more than what I can confirm here, please refer to your salesman."

FAMILY = [
    "SRTWC286-SH",
    "SRTWC286-SH-150",
    "SRTWC286-SH-200",
    "SRTWC286-SH-NEW",
    "SRTWC286-SH-NEW-150",
    "SRTWC286-SH-NEW-200",
    "SRTWC286-SH-NEW-P",
    "SRTWC286-SH-P",
    "SRTWC286-SH-PP",
    "SRTWC286-SH-UF",
]
#: The catalogue the owner's sessions touched: the family, and the two SRTWC287 codes of
#: rows 9 to 12 (SRTWC287-S-150-RL is the product round 7's row 12 wrongly added).
CATALOGUE = [*FAMILY, "SRTWC287-S-150", "SRTWC287-S-150-RL"]

FAMILY_LIST = "\n".join(
    ["SRTWC286 matches 10 products. Which one?", *[f"{i}. {c}" for i, c in enumerate(FAMILY, 1)]]
)


def _point_form(filled: dict[str, int] | None = None, codes: list[str] = FAMILY) -> str:
    filled = filled or {}
    return "\n".join(
        [
            "How many units for each?",
            *[f"{i}. {c} - {filled.get(c, '')}" for i, c in enumerate(codes, 1)],
        ]
    )


def _answered(pairs: list[tuple[str, int]]) -> str:
    return "\n\n".join(f"{code} x {qty}: {TOO_BIG}" for code, qty in pairs)


def v(**overrides: Any) -> dict[str, Any]:
    """The parser's answer: every declared key, nothing said unless overridden."""
    base = {
        "message_type": "business_query",
        "intent_hint": None,
        "domain_hint": None,
        "demand_qty": None,
        "entities": [],
        "reference_positions": [],
        "open_question_answer": answer(None),
    }
    base.update(overrides)
    return _parser_output(**base)


def ask(raw: str, *, confident: bool = False) -> dict[str, Any]:
    """"check stock <raw>": the stock question naming one product token."""
    return v(
        domain_hint="inventory",
        intent_hint="check_stock",
        entities=[entity(raw, hint="product", confident=confident)],
    )


def coded(code: str, qty: int | None = None) -> dict[str, Any]:
    return entity(code, hint="product", quantity=qty)


class Stack:
    """The console on contact 437264483: one `engine.run_turn` per message, the session
    carried in `respond_contacts.session_vars` from turn to turn."""

    def __init__(self, session_factory, stub_parser, monkeypatch) -> None:
        from app.services.ai_assistant_service import MCPRuntimeClient
        from sorento_crm_mcp.presenters import present_response

        self.session_factory = session_factory
        self.stub_parser = stub_parser
        self.blocks: list[str] = []
        self.transcript: list[str] = []
        self.stock_calls: list[dict[str, Any]] = []
        self.turns = 0

        def _tool(_client, name: str, args: dict[str, Any]) -> str:
            if name != "crm_inventory_stock_balance_list":
                return json.dumps({"answers": []})
            self.stock_calls.append(dict(args))
            codes = {
                str(row[0]): row[1]
                for row in session_factory().execute(
                    text("SELECT id, product_code FROM products")
                ).all()
            }
            quantities = json.loads(args.get("requested_quantities") or "{}")
            rows = []
            for pid in args.get("product_ids") or []:
                qty = quantities.get(pid)
                rows.append(
                    {
                        "product_id": pid,
                        "product_code": codes[pid],
                        "product_name": codes[pid],
                        "needs_quantity": qty is None,
                        "requested_qty": qty,
                        **({"branch": "too_big"} if qty is not None else {}),
                    }
                )
            raw = {
                "data": [],
                "stock_visibility": {"mode": "availability"},
                "stock_availability": rows,
            }
            return present_response(name, json.dumps(raw))

        monkeypatch.setattr(MCPRuntimeClient, "call_tool", _tool)
        # The owner's console contact is a dealer: "Availability only".
        monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: True)

    def say(self, message: str, parsed: dict[str, Any]) -> str:
        self.turns += 1
        self.stub_parser(parsed, on_call=self.blocks.append)
        envelope = _envelope(
            message={
                "event_type": "message.received",
                "contact": {"id": CONTACT_ID},
                "message": {
                    "messageId": f"ZZT-1293-{self.turns}",
                    "contactId": CONTACT_ID,
                    "channelId": "whatsapp",
                    "traffic": "incoming",
                    "message": {"type": "text", "text": message},
                },
            }
        )
        result = engine_mod.run_turn(envelope, session_factory=self.session_factory)
        assert result.status == "done", (message, result.status, result.stage)
        reply = (result.reply or {}).get("text") or ""
        self.transcript += [message, f"-> {reply}"]
        return reply

    def open_question(self) -> dict[str, Any] | None:
        row = self.session_factory().execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        ).scalar()
        return (row or {}).get("open_question")

    def block_object(self, index: int = -1) -> dict[str, Any] | None:
        for line in self.blocks[index].splitlines():
            if line.startswith("Open question: "):
                return json.loads(line[len("Open question: ") :])
        return None


@pytest.fixture()
def stack(session_factory, stub_parser, stub_access, monkeypatch) -> Stack:
    _seed_contact(session_factory, phone="+60000001293")
    _link_contact_company(session_factory, company_id=SORENTO)
    _seed_products(session_factory, CATALOGUE)
    stub_access()
    return Stack(session_factory, stub_parser, monkeypatch)


def _all_ten() -> dict[str, Any]:
    return answer("pick", [item(i) for i in range(1, 11)])


# --------------------------------------------------------------------------- #
# 14:06Z: the did-you-mean, "the first one, I need 2" (the issue's own exchange)
# --------------------------------------------------------------------------- #


def test_the_owner_1406_session(stack):
    reply = stack.say("check stock STWC2867", ask("STWC2867", confident=True))
    assert reply == "Couldn't find STWC2867. Did you mean:\n1. SRTWC286-SH\n2. SRTWC286-SH-P"

    reply = stack.say(
        "the first one, I need 2",
        v(demand_qty=2, reference_positions=[1], open_question_answer=answer("pick", [item(1, None, 2)])),
    )
    # The parser was shown the pick as an object, owing the pick and the quantity.
    assert stack.block_object() == {
        "kind": "pick_one",
        "options": [
            {"position": 1, "code": "SRTWC286-SH"},
            {"position": 2, "code": "SRTWC286-SH-P"},
        ],
        "owed": ["pick", "qty"],
    }
    assert reply == _answered([("SRTWC286-SH", 2)])
    assert stack.open_question() is None

    reply = stack.say(
        "1, I need 2",
        v(demand_qty=2, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 2)])),
    )
    assert stack.block_object()["kind"] == "quantities"
    assert stack.block_object()["status"] == "answered"
    assert reply == _answered([("SRTWC286-SH", 2)])

    reply = stack.say(
        "SRTWC286-SH x 2", v(domain_hint="inventory", entities=[coded("SRTWC286-SH", 2)])
    )
    assert reply == _answered([("SRTWC286-SH", 2)])
    # No reply after the did-you-mean repeats the code the resolver did not recognise.
    assert not any("STWC2867" in line for line in stack.transcript[3::2])


def test_the_owner_1406_session_with_the_live_v32_reading(stack):
    """The same message read by a prompt that declares nothing (the live v32 label until
    the republish): a position beside a quantity. The shape fallback answers it too."""
    stack.say("check stock STWC2867", ask("STWC2867", confident=True))
    reply = stack.say("the first one, I need 2", v(demand_qty=2, reference_positions=[1]))
    assert reply == _answered([("SRTWC286-SH", 2)])


def test_a_quantity_alone_under_the_did_you_mean_never_repeats_the_miss(stack):
    stack.say("check stock STWC2867", ask("STWC2867", confident=True))
    reply = stack.say("I need 2", v(demand_qty=2))
    assert reply == "Which one do you need 2 of?\n1. SRTWC286-SH\n2. SRTWC286-SH-P"
    assert stack.block_object(-1)["owed"] == ["pick", "qty"]
    reply = stack.say("the second", v(open_question_answer=answer("pick", [item(2)])))
    assert stack.block_object(-1) == {
        "kind": "pick_one",
        "options": [
            {"position": 1, "code": "SRTWC286-SH"},
            {"position": 2, "code": "SRTWC286-SH-P"},
        ],
        "owed": ["pick"],
        "qty": 2,
    }
    assert reply == _answered([("SRTWC286-SH-P", 2)])


# --------------------------------------------------------------------------- #
# 07:18Z: the round 3 hand test
# --------------------------------------------------------------------------- #


def test_the_owner_0718_session(stack):
    assert stack.say("check stock srtwc286", ask("srtwc286")) == FAMILY_LIST
    reply = stack.say("1", v(reference_positions=[1], open_question_answer=answer("pick", [item(1)])))
    assert stack.block_object()["kind"] == "pick_one"
    assert len(stack.block_object()["options"]) == 10
    assert reply == "How many units of SRTWC286-SH?"
    reply = stack.say("10", v(demand_qty=10, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 10)])))
    assert stack.block_object()["status"] == "asked"
    assert reply == _answered([("SRTWC286-SH", 10)])
    # The picker is not sticky: "2" revises the answered quantity, never picks line 2.
    reply = stack.say("2", v(demand_qty=2, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 2)])))
    assert stack.block_object()["status"] == "answered"
    assert reply == _answered([("SRTWC286-SH", 2)])
    reply = stack.say("3", v(demand_qty=3, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 3)])))
    assert reply == _answered([("SRTWC286-SH", 3)])


# --------------------------------------------------------------------------- #
# 08:18Z: the round 4 console test
# --------------------------------------------------------------------------- #


def test_the_owner_0818_session(stack):
    assert stack.say("check stock srtwc286", ask("srtwc286")) == FAMILY_LIST
    reply = stack.say("all", v(reference_positions=list(range(1, 11)), open_question_answer=_all_ten()))
    assert reply == _point_form()
    reply = stack.say(
        "1. 10, 2. 5",
        v(open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 10), item(2, "SRTWC286-SH-150", 5)])),
    )
    assert stack.block_object()["owed"] == list(range(1, 11))
    assert reply == _point_form({"SRTWC286-SH": 10, "SRTWC286-SH-150": 5})
    # One bare number over the still-asked point form: every line still owed (AC-SA333).
    reply = stack.say("10", v(demand_qty=10))
    assert reply == _answered(
        [("SRTWC286-SH", 10), ("SRTWC286-SH-150", 5), *[(c, 10) for c in FAMILY[2:]]]
    )
    # "tia" (tiga, 3) after a ten-product answer does not say which product: asked,
    # with the full count, never a silent default.
    reply = stack.say("tia", v(demand_qty=3))
    assert reply == "\n".join(
        ["Is 3 for all 10 products, or for one of them?", *[f"{i}. {c}" for i, c in enumerate(FAMILY, 1)]]
    )


# --------------------------------------------------------------------------- #
# 10:11Z: the round 7 console test, rows 1 to 12
# --------------------------------------------------------------------------- #


def test_the_owner_1011_session(stack):
    # Row 1.
    assert stack.say("check stock srtwc286", ask("srtwc286")) == FAMILY_LIST
    # Row 2: "semua of them" = all.
    reply = stack.say("semua of them", v(open_question_answer=_all_ten()))
    assert reply == _point_form()
    # Row 3: one number per line = positions in order.
    reply = stack.say(
        "10\n20\n30\n40\n5",
        v(
            open_question_answer=answer(
                "fill", [item(i, None, q) for i, q in enumerate([10, 20, 30, 40, 5], 1)]
            )
        ),
    )
    assert reply == _point_form(dict(zip(FAMILY, [10, 20, 30, 40, 5])))
    # Row 4: the list pasted back, 1 = 10, 2 = 5, the rest blank: the whole answer.
    reply = stack.say(
        "check stock\n" + _point_form({"SRTWC286-SH": 10, "SRTWC286-SH-150": 5}).split("\n", 1)[1],
        v(
            domain_hint="inventory",
            open_question_answer=answer(
                "done", [item(1, "SRTWC286-SH", 10), item(2, "SRTWC286-SH-150", 5)]
            ),
        ),
    )
    assert reply == (
        _answered([("SRTWC286-SH", 10), ("SRTWC286-SH-150", 5)])
        + "\nNot checked: "
        + ", ".join(FAMILY[2:])
        + "."
    )
    # Row 5: pasted again, over the answer: answered again.
    reply = stack.say(
        _point_form({"SRTWC286-SH": 10, "SRTWC286-SH-150": 5}).split("\n", 1)[1],
        v(
            open_question_answer=answer(
                "fill", [item(1, "SRTWC286-SH", 10), item(2, "SRTWC286-SH-150", 5)]
            ),
        ),
    )
    assert reply == _answered([("SRTWC286-SH", 10), ("SRTWC286-SH-150", 5)])
    stock_calls = len(stack.stock_calls)
    # Row 6: "that's it" with nothing left open fetches nothing and asks nothing.
    reply = stack.say("that's it", v(message_type="casual", open_question_answer=answer("done")))
    assert len(stack.stock_calls) == stock_calls
    assert "How many" not in reply and "Which one" not in reply
    # Row 7: the typo placed silently on SRTWC286-SH-150.
    assert stack.say("check stock SRTWC286-SH-15", ask("SRTWC286-SH-15", confident=True)) == (
        "How many units of SRTWC286-SH-150?"
    )
    reply = stack.say("5", v(demand_qty=5, open_question_answer=answer("fill", [item(1, "SRTWC286-SH-150", 5)])))
    assert reply == _answered([("SRTWC286-SH-150", 5)])
    # Row 8: a did-you-mean of three, "3", "50", "howa bout 30".
    reply = stack.say("SRTWC286-150", ask("SRTWC286-150", confident=True))
    assert reply.endswith("Did you mean:\n1. SRTWC286-SH-150\n2. SRTWC287-S-150\n3. SRTWC286-SH")
    assert stack.say("3", v(reference_positions=[3], open_question_answer=answer("pick", [item(3)]))) == (
        "How many units of SRTWC286-SH?"
    )
    assert stack.say("50", v(demand_qty=50, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 50)]))) == (
        _answered([("SRTWC286-SH", 50)])
    )
    assert stack.say(
        "howa bout 30",
        v(demand_qty=30, correction=True, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 30)])),
    ) == _answered([("SRTWC286-SH", 30)])
    # Row 9: three named products with their own quantities, every one answered.
    three = [("SRTWC286-SH-150", 5), ("SRTWC287-S-150", 10), ("SRTWC286-SH", 1)]
    reply = stack.say(
        "1. SRTWC286-SH-150 - 5\n2. SRTWC287-S-150 - 10\n3. SRTWC286-SH - 1",
        v(domain_hint="inventory", entities=[coded(c, q) for c, q in three]),
    )
    assert reply == _answered(three)
    # Row 10: "how about 3 for all of them" = the three just answered.
    reply = stack.say("how about 3 for all of them", v(open_question_answer=answer("all", qty_for_all=3)))
    assert reply == _answered([(c, 3) for c, _ in three])
    # Row 11: the same three lines at 3 each.
    reply = stack.say(
        "1. SRTWC286-SH-150 - 3\n2. SRTWC287-S-150 - 3\n3. SRTWC286-SH - 3",
        v(open_question_answer=answer("fill", [item(i, c, 3) for i, (c, _) in enumerate(three, 1)])),
    )
    assert reply == _answered([(c, 3) for c, _ in three])
    # Row 12: a bare "10" asks which, over the SAME three, never a bigger list.
    reply = stack.say("10", v(demand_qty=10))
    assert reply == (
        "Is 10 for all 3 products, or for one of them?\n"
        "1. SRTWC286-SH-150\n2. SRTWC287-S-150\n3. SRTWC286-SH"
    )
    assert "SRTWC287-S-150-RL" not in reply
    assert stack.block_object()["kind"] == "quantities"
    # And the answer to row 12's question.
    reply = stack.say("all", v(open_question_answer=answer("all")))
    assert stack.block_object()["asked_qty"] == 10
    assert reply == _answered([(c, 10) for c, _ in three])

