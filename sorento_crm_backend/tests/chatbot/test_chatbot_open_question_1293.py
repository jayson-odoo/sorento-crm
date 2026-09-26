"""Issue #1293: every question the bot asks is ONE open-question object the parser answers.

Owner, 26 Sep 2026 ~14:15Z, after the round 8 console test of PR #1247: "I want to say
'the first one I need two'. It's quite weird that it replies in that way. So maybe our
parser can be better ... not too much hard coding, hard routing."

The exchange (:3087, 14:07Z to 14:08Z):

    check stock STWC2867 ...
    -> Couldn't find STWC2867. Did you mean:
       1. SRTWC286-SH
       2. SRTWC286-SH-P
    the first one, I need 2
    -> STWC2867 x 2: which one? 1. SRTWC286-SH 2. SRTWC286-SH-P     <- the defect
    1, I need 2
    -> the same reply again                                           <- the defect
    SRTWC286-SH x 2
    -> SRTWC286-SH x 2: the quantity is more than what I can confirm here, ...

The design rule (the plan's "Method"): the LLM parser READS, the code APPLIES. Any
question the bot asks is written as an open question object (`turn/question.py`), the
parser returns one declared answer object (`open_question_answer`) and `turn/apply.py`
acts on it. The shape rules are the fallback only, for a verdict that declares nothing.

Only the parser is stubbed, as it should answer. Everything after it is the real code.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.services.chatbot import dealer_stock
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.turn import pending as turn_pending
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.state import Focus

from tests.chatbot import _ht26_fixtures as ht
from tests.chatbot._turn_helpers import build_policy, verdict
from tests.chatbot.test_stock_ask_ht26_r4_owner_replay import TOO_BIG, Console

#: The owner's did-you-mean, as the console printed it.
DYM = ["SRTWC286-SH", "SRTWC286-SH-P"]
#: A three-option did-you-mean, for "the third", "1 and 3", "both" and the rest.
DYM3 = ["SRTWC286-SH", "SRTWC286-SH-P", "SRTWC286-SH-150"]
OWNER_DYM_TEXT = "Couldn't find STWC2867. Did you mean:\n1. SRTWC286-SH\n2. SRTWC286-SH-P"


def item(position: int | None = None, code: str | None = None, qty: int | None = None):
    return {"position": position, "code": code, "qty": qty}


def answer(mode: str | None, items=(), qty_for_all: int | None = None) -> dict[str, Any]:
    """The declared answer object, as the parser emits it."""
    return {"mode": mode, "items": list(items), "qty_for_all": qty_for_all}


def _candidates(codes: list[str]) -> list[dict[str, Any]]:
    return [{"product": code, "uuid": ht.uuid_of(code), "entity_type": "product"} for code in codes]


class DymConsole(Console):
    """The dealer conversation from the did-you-mean on: the resolver missed the typed
    code and the reply offered its trigram neighbours (`dealer_stock.did_you_mean`)."""

    def first_ask(self, message: str, *, typed: str = "STWC2867", codes=None, quantity=None) -> str:
        text, pick = dealer_stock.did_you_mean(
            typed, _candidates(codes or DYM), quantity=quantity, asked_at_turn=1
        )
        # The miss stays on the focus: a product row the resolver never placed (no uuid).
        missed = {
            "raw": typed,
            "hint": "product",
            "canonical_code": typed.upper(),
            "current_message": False,
            "confident": False,
            **({"quantity": quantity} if quantity is not None else {}),
        }
        self.state = replace(
            self.state,
            focus=Focus(products=[missed], domains=["inventory"]),
            pending=pick,
            turn_no=1,
        )
        self.transcript += [message, f"-> {text}"]
        return text


def _numbered(head: str, codes: list[str]) -> str:
    return "\n".join([head, *[f"{i}. {code}" for i, code in enumerate(codes, 1)]])


def _point_form(codes: list[str]) -> str:
    return "\n".join(
        [task_mod.EACH_QUESTION, *[f"{i}. {code} - " for i, code in enumerate(codes, 1)]]
    )


# --------------------------------------------------------------------------- #
# W1: the open question object, one per question the bot asks
# --------------------------------------------------------------------------- #


def test_the_question_kinds_are_the_owners():
    assert question_mod.QUESTION_KINDS == (
        "pick_one",
        "quantities",
        "confirm",
        "choose_brand",
        "free",
    )


def test_a_did_you_mean_list_is_a_pick_one_owing_the_pick_and_the_quantity():
    _text, pick = dealer_stock.did_you_mean("STWC2867", _candidates(DYM))
    assert question_mod.open_question(pick, ()) == {
        "kind": "pick_one",
        "options": [
            {"position": 1, "code": "SRTWC286-SH"},
            {"position": 2, "code": "SRTWC286-SH-P"},
        ],
        "owed": ["pick", "qty"],
    }


def test_the_object_never_carries_the_code_the_resolver_did_not_recognise():
    _text, pick = dealer_stock.did_you_mean("STWC2867", _candidates(DYM), quantity=4)
    shown = question_mod.open_question(pick, ())
    assert "STWC2867" not in repr(shown)
    assert shown["owed"] == ["pick"] and shown["qty"] == 4


def test_a_one_option_did_you_mean_is_a_confirm():
    _text, pick = dealer_stock.did_you_mean("ELP3753", _candidates(["ELP3754"]))
    shown = question_mod.open_question(pick, ())
    assert shown["kind"] == "confirm"
    assert shown["options"] == [{"position": 1, "code": "ELP3754"}]
    assert shown["owed"] == ["yes_no", "qty"]


def test_a_yes_no_offer_is_a_confirm():
    offer = turn_pending.ask(
        "team_pick",
        [{"position": 1, "label": "Warehouse", "team": "warehouse"}],
        expects="yes_no",
    )
    shown = question_mod.open_question(offer, ())
    assert shown["kind"] == "confirm" and shown["owed"] == ["yes_no"]


def test_a_customer_roster_is_a_pick_one_with_its_names():
    roster = turn_pending.ask(
        "customer_pick",
        [
            {"position": 1, "label": "CHIN CHUN HARDWARE", "code": "300-C001", "entity_type": "customer"},
            {"position": 2, "label": "CHIN CHUN TIMBER", "code": "300-C002", "entity_type": "customer"},
        ],
    )
    shown = question_mod.open_question(roster, ())
    assert shown["kind"] == "pick_one"
    assert shown["options"][0] == {"position": 1, "code": "300-C001", "label": "CHIN CHUN HARDWARE"}
    assert shown["owed"] == ["pick"]


def test_a_brand_roster_is_choose_brand():
    shown = question_mod.open_question(_brand_pick(), ())
    assert shown["kind"] == "choose_brand"
    assert [o["code"] for o in shown["options"]] == ["SORENTO", "ELITE", "MODENA"]


def test_a_question_with_no_options_is_free():
    shown = question_mod.open_question(turn_pending.ask("outstanding_detail", []), ())
    assert shown == {"kind": "free", "options": [], "owed": ["reply"]}


def test_the_stock_quantities_question_is_quantities_asked_then_answered():
    asked = ht.stock_task([("SRTWC286-SH", 10), ("SRTWC286-SH-150", None)])
    shown = question_mod.open_question(None, (asked,))
    assert shown == {
        "kind": "quantities",
        "status": "asked",
        "items": [
            {"position": 1, "code": "SRTWC286-SH", "qty": 10},
            {"position": 2, "code": "SRTWC286-SH-150", "qty": None},
        ],
        "owed": [2],
    }
    answered = ht.stock_task([("SRTWC286-SH", 10)], status=task_mod.ANSWERED)
    assert question_mod.open_question(None, (answered,))["status"] == "answered"


def test_the_pending_question_is_the_one_on_the_table_over_a_stock_task():
    _text, pick = dealer_stock.did_you_mean("STWC2867", _candidates(DYM))
    asked = ht.stock_task([("ELP3754", None)])
    assert question_mod.open_question(pick, (asked,))["kind"] == "pick_one"


# --------------------------------------------------------------------------- #
# W1: the declared answer, strict-schema safe, and the prompt contract
# --------------------------------------------------------------------------- #


def test_the_answer_object_declares_pick_yes_and_no_strict_safe():
    node = parser_mod.PARSE_OUTPUT_JSON_SCHEMA["properties"]["open_question_answer"]
    assert node["additionalProperties"] is False
    assert sorted(node["required"]) == sorted(node["properties"])
    assert node["properties"]["mode"]["enum"] == [
        "pick",
        "yes",
        "no",
        "fill",
        "all",
        "done",
        "cancel",
        None,
    ]
    items = node["properties"]["items"]["items"]
    assert items["additionalProperties"] is False
    assert sorted(items["required"]) == ["code", "position", "qty"]
    assert "open_question_answer" in parser_mod.TOLERATED_ABSENT


def test_the_prompt_states_every_kind_and_every_mode():
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT, STOCK_TASK_ADDENDUM

    assert STOCK_TASK_ADDENDUM in SEMANTIC_PARSER_PROMPT
    section = STOCK_TASK_ADDENDUM.split("== THE OPEN QUESTION AND open_question_answer ==", 1)[1]
    # Each kind is DEFINED (its own line), not merely named in passing.
    for kind in question_mod.QUESTION_KINDS:
        assert f'\n  "{kind}": ' in section, kind
    # The declared answer, every mode, exactly as the schema enumerates them.
    assert (
        '"open_question_answer": {"mode": '
        '"pick"|"yes"|"no"|"fill"|"all"|"done"|"cancel"|null,'
    ) in section
    for mode in ("pick", "yes", "no", "fill", "all", "done", "cancel"):
        assert f'-> "{mode}"' in section, mode
    # The owner's own message is taught as ONE pick carrying its quantity.
    assert (
        '"the first one, I need 2", "1, I need 2", "yang pertama, 2 unit", "第一个要两个"\n'
        '    -> "pick", items [{"position": 1, "code": null, "qty": 2}]'
    ) in section
    # The owner's own phrase, and ordinals and numbers in all three languages.
    for phrase in (
        "the first one, I need 2",
        "the second",
        "both",
        "1 and 3",
        "yang pertama",
        "dua",
        "第一个",
        "san ge",
        "none of them",
    ):
        assert phrase in section, phrase
    # The retired kind names are gone from the contract.
    assert '"stock_quantities"' not in section and '"last_answer"' not in section


def test_the_user_block_states_the_open_pick_as_one_json_line():
    _text, pick = dealer_stock.did_you_mean("STWC2867", _candidates(DYM))
    block = parser_mod.build_user_block(
        previous_response=OWNER_DYM_TEXT,
        latest_user_message="the first one, I need 2",
        pending_kind=pick.kind,
        pending_options=[o["label"] for o in pick.options],
        open_question=question_mod.open_question(pick, ()),
    )
    assert (
        'Open question: {"kind":"pick_one","options":[{"position":1,"code":"SRTWC286-SH"},'
        '{"position":2,"code":"SRTWC286-SH-P"}],"owed":["pick","qty"]}'
    ) in block


def test_the_task_hint_points_at_the_object_only_when_the_object_is_the_quantities():
    """Under an open pick the object is the pick's, so a multi-line stock question the
    focus also carries prints its own lines (round 8, review S5)."""
    _text, pick = dealer_stock.did_you_mean("STWC2867", _candidates(DYM))
    asked = ht.stock_task([("ELP3754", None), ("SRTKT1631SS", None)])
    block = parser_mod.build_user_block(
        previous_response="x",
        latest_user_message="y",
        pending_kind=pick.kind,
        focus=Focus(tasks=(asked,)),
        open_question=question_mod.open_question(pick, (asked,)),
    )
    assert "see Open question" not in block
    assert "1. ELP3754 -; 2. SRTKT1631SS -" in block


# --------------------------------------------------------------------------- #
# W2: the owner's exchange, 26 Sep 14:07Z
# --------------------------------------------------------------------------- #


def _owner_dym() -> DymConsole:
    console = DymConsole()
    assert console.first_ask("check stock STWC2867") == OWNER_DYM_TEXT
    return console


def test_the_first_one_i_need_2_picks_and_answers_in_one_message():
    console = _owner_dym()
    reply = console.say(
        "the first one, I need 2",
        verdict(
            demand_qty=2,
            reference_positions=[1],
            open_question_answer=answer("pick", [item(1, "SRTWC286-SH", 2)]),
        ),
    )
    assert reply == f"SRTWC286-SH x 2: {TOO_BIG}"
    assert "open_question_answer_pick" in console.plans[-1].trace.rules_fired
    assert console.state.pending is None


def test_the_object_alone_drives_the_pick_with_no_positions_beside_it():
    console = _owner_dym()
    reply = console.say(
        "1, I need 2",
        verdict(demand_qty=2, open_question_answer=answer("pick", [item(1, None, 2)])),
    )
    assert reply == f"SRTWC286-SH x 2: {TOO_BIG}"


def test_the_object_wins_over_a_position_the_quantity_was_misread_as():
    """"no 2, 5 units": a shape-only reading could take 5 as a second position. The
    declared answer says one pick at 5, and it is what is applied."""
    console = DymConsole()
    console.first_ask("check stock STWC2867", codes=DYM3)
    reply = console.say(
        "no 2, 5 units",
        verdict(
            is_affirmative=False,
            demand_qty=5,
            reference_positions=[2, 5],
            open_question_answer=answer("pick", [item(2, "SRTWC286-SH-P", 5)]),
        ),
    )
    assert reply == f"SRTWC286-SH-P x 5: {TOO_BIG}"


def test_the_shape_fallback_answers_a_position_and_a_quantity_too():
    """A verdict that declares nothing (the live v32 prompt, a recorded emission): a
    position on the list beside a quantity is the pick at that quantity, never the pick
    asked again with the quantity riding on it."""
    console = _owner_dym()
    reply = console.say("the first one, I need 2", verdict(demand_qty=2, reference_positions=[1]))
    assert reply == f"SRTWC286-SH x 2: {TOO_BIG}"
    assert "stock_pick_position_takes_quantity" in console.plans[-1].trace.rules_fired


def test_a_quantity_with_no_pick_asks_again_without_the_unrecognised_code():
    console = _owner_dym()
    reply = console.say("I need 2", verdict(demand_qty=2))
    assert reply == _numbered("Which one do you need 2 of?", DYM)
    assert "STWC2867" not in reply
    # The quantity rides on the pick; the next message picks and is answered.
    reply = console.say("1", verdict(open_question_answer=answer("pick", [item(1, "SRTWC286-SH")])))
    assert reply == f"SRTWC286-SH x 2: {TOO_BIG}"


def test_the_family_pick_still_leads_with_the_family_the_dealer_typed():
    """"srtwc286" was recognised (it placed ten products), so its header stays."""
    assert task_mod.pick_question("SRTWC286", ["A", "B"], 88).startswith("SRTWC286 x 88: which one?")


def test_the_owner_exchange_replayed_after_the_fix():
    console = _owner_dym()
    console.say(
        "the first one, I need 2",
        verdict(
            demand_qty=2,
            reference_positions=[1],
            open_question_answer=answer("pick", [item(1, "SRTWC286-SH", 2)]),
        ),
    )
    # The pick is closed and the check answered, so "1, I need 2" now revises the
    # answered check (its one line) rather than picking from a closed list.
    console.say(
        "1, I need 2",
        verdict(demand_qty=2, open_question_answer=answer("fill", [item(1, "SRTWC286-SH", 2)])),
    )
    console.say(
        "SRTWC286-SH x 2",
        verdict(domain_hint="inventory", entities=[ht.asked("SRTWC286-SH", 2)]),
    )
    assert console.transcript == [
        "check stock STWC2867",
        f"-> {OWNER_DYM_TEXT}",
        "the first one, I need 2",
        f"-> SRTWC286-SH x 2: {TOO_BIG}",
        "1, I need 2",
        f"-> SRTWC286-SH x 2: {TOO_BIG}",
        "SRTWC286-SH x 2",
        f"-> SRTWC286-SH x 2: {TOO_BIG}",
    ]
    assert not any("STWC2867" in line for line in console.transcript[2:])


# --------------------------------------------------------------------------- #
# W3 / W4: ten natural phrasings per question kind
# --------------------------------------------------------------------------- #

#: (message, declared answer, what the reply must be). Over DYM3, no quantity carried.
PICK_ONE_PHRASINGS = [
    ("the first one", answer("pick", [item(1)]), "How many units of SRTWC286-SH?"),
    ("second", answer("pick", [item(2)]), "How many units of SRTWC286-SH-P?"),
    ("the third", answer("pick", [item(3)]), "How many units of SRTWC286-SH-150?"),
    ("SRTWC286-SH-P", answer("pick", [item(None, "SRTWC286-SH-P")]), "How many units of SRTWC286-SH-P?"),
    ("yang pertama", answer("pick", [item(1)]), "How many units of SRTWC286-SH?"),
    ("dua", answer("pick", [item(2)]), "How many units of SRTWC286-SH-P?"),
    ("第一个", answer("pick", [item(1)]), "How many units of SRTWC286-SH?"),
    ("1 and 3", answer("pick", [item(1), item(3)]), _point_form(["SRTWC286-SH", "SRTWC286-SH-150"])),
    ("the first one, I need 2", answer("pick", [item(1, None, 2)]), f"SRTWC286-SH x 2: {TOO_BIG}"),
    ("yang kedua, 10 unit", answer("pick", [item(2, None, 10)]), f"SRTWC286-SH-P x 10: {TOO_BIG}"),
    ("第一个要两个", answer("pick", [item(1, None, 2)]), f"SRTWC286-SH x 2: {TOO_BIG}"),
    (
        "both, 3 each",
        answer("pick", [item(1), item(2)], qty_for_all=3),
        f"SRTWC286-SH x 3: {TOO_BIG}\nSRTWC286-SH-P x 3: {TOO_BIG}",
    ),
    ("none of them", answer("no"), task_mod.REFER_TO_SALESMAN),
]


@pytest.mark.parametrize(
    "message,declared,expected", PICK_ONE_PHRASINGS, ids=[p[0] for p in PICK_ONE_PHRASINGS]
)
def test_pick_one_phrasings(message, declared, expected):
    """Only the declared answer is stubbed: no `reference_positions`, no
    `is_affirmative`, so the object alone is what the engine acts on."""
    console = DymConsole()
    console.first_ask("check stock STWC2867", codes=DYM3)
    assert console.say(message, verdict(open_question_answer=declared)) == expected
    assert "STWC2867" not in console.transcript[-1]


#: One-option did-you-mean: "Couldn't find ELP3753. Did you mean ELP3754?"
CONFIRM_PHRASINGS = [
    ("yes", answer("yes"), "How many units of ELP3754?"),
    ("ya", answer("yes"), "How many units of ELP3754?"),
    ("ok", answer("yes"), "How many units of ELP3754?"),
    ("betul", answer("yes"), "How many units of ELP3754?"),
    ("对", answer("yes"), "How many units of ELP3754?"),
    ("yes, 5 units", answer("yes", qty_for_all=5), f"ELP3754 x 5: {TOO_BIG}"),
    ("ya, 10", answer("yes", [item(1, "ELP3754", 10)]), f"ELP3754 x 10: {TOO_BIG}"),
    ("no", answer("no"), task_mod.REFER_TO_SALESMAN),
    ("tak", answer("no"), task_mod.REFER_TO_SALESMAN),
    ("不是", answer("no"), task_mod.REFER_TO_SALESMAN),
]


@pytest.mark.parametrize(
    "message,declared,expected", CONFIRM_PHRASINGS, ids=[p[0] for p in CONFIRM_PHRASINGS]
)
def test_confirm_phrasings(message, declared, expected):
    console = DymConsole()
    first = console.first_ask("check stock ELP3753", typed="ELP3753", codes=["ELP3754"])
    assert first == "Couldn't find ELP3753. Did you mean ELP3754?"
    assert console.say(message, verdict(open_question_answer=declared)) == expected


def test_a_confirm_keeps_the_quantity_the_miss_was_asked_with():
    console = DymConsole()
    console.first_ask("check stock ELP3753 10", typed="ELP3753", codes=["ELP3754"], quantity=10)
    assert console.say("ya", verdict(open_question_answer=answer("yes"))) == f"ELP3754 x 10: {TOO_BIG}"


#: Over "How many units of SRTWC286-SH?" (one product, asked).
QUANTITY_PHRASINGS = [
    ("10", 10),
    ("sepuluh", 10),
    ("十个", 10),
    ("san ge", 3),
    ("tiga", 3),
    ("tia", 3),
    ("10 pcs", 10),
    ("I need 20", 20),
    ("nak 5 unit", 5),
    ("要五个", 5),
]


@pytest.mark.parametrize("message,qty", QUANTITY_PHRASINGS, ids=[p[0] for p in QUANTITY_PHRASINGS])
def test_quantities_phrasings(message, qty):
    console = Console()
    console.state = ht.state(
        Focus(
            products=ht.product_rows("SRTWC286-SH"),
            domains=["inventory"],
            tasks=(ht.stock_task([("SRTWC286-SH", None)]),),
        ),
        availability_only=True,
        turn_no=2,
    )
    reply = console.say(message, verdict(open_question_answer=answer("fill", [item(1, "SRTWC286-SH", qty)])))
    assert reply == f"SRTWC286-SH x {qty}: {TOO_BIG}"


def _brand_pick():
    return turn_pending.ask(
        "brand_pick",
        [
            {"position": 1, "label": "Sorento", "code": "SORENTO", "entity_type": "brand"},
            {"position": 2, "label": "Elite", "code": "ELITE", "entity_type": "brand"},
            {"position": 3, "label": "Modena", "code": "MODENA", "entity_type": "brand"},
        ],
        asked_at_turn=3,
        payload={"domain": "promotion", "domains": ["promotion"]},
    )


CHOOSE_BRAND_PHRASINGS = [
    ("Sorento", answer("pick", [item(None, "SORENTO")]), ["SORENTO"]),
    ("the first", answer("pick", [item(1)]), ["SORENTO"]),
    ("2", answer("pick", [item(2)]), ["ELITE"]),
    ("modena one", answer("pick", [item(None, "MODENA")]), ["MODENA"]),
    ("yang kedua", answer("pick", [item(2)]), ["ELITE"]),
    ("第三个", answer("pick", [item(3)]), ["MODENA"]),
    ("tiga", answer("pick", [item(3)]), ["MODENA"]),
    ("elite and modena", answer("pick", [item(2), item(3)]), ["ELITE", "MODENA"]),
    ("1 and 3", answer("pick", [item(1), item(3)]), ["SORENTO", "MODENA"]),
    ("all of them", answer("pick", [item(1), item(2), item(3)]), ["SORENTO", "ELITE", "MODENA"]),
]


@pytest.mark.parametrize(
    "message,declared,brands", CHOOSE_BRAND_PHRASINGS, ids=[p[0] for p in CHOOSE_BRAND_PHRASINGS]
)
def test_choose_brand_phrasings(message, declared, brands):
    state = ht.state(Focus(domains=["promotion"]), pending=_brand_pick(), turn_no=4)
    applied, plan = apply(state, verdict(open_question_answer=declared), build_policy())
    assert "answer_pending" in plan.trace.rules_fired
    assert "open_question_answer_pick" in plan.trace.rules_fired
    assert list(applied.focus.brands) == brands
    assert applied.focus.domains == ["promotion"]


#: "Not an answer, with the new ask": mode null, and the rest of the verdict IS the new
#: ask. The pick is never answered by it.
NOT_AN_ANSWER_PHRASINGS = [
    ("check stock ELP3754", verdict(domain_hint="inventory", entities=[ht.asked("ELP3754")])),
    ("ELP3754 x 5", verdict(domain_hint="inventory", entities=[ht.asked("ELP3754", 5)])),
    ("any promo?", verdict(domain_hint="promotion", intent_hint="check_promo")),
    ("price for SRTKT1631SS", verdict(domain_hint="master_products", entities=[ht.asked("SRTKT1631SS")])),
    ("hi", verdict(message_type="casual")),
    ("thanks", verdict(message_type="casual")),
    ("who is my salesman?", verdict(message_type="casual")),
    ("stok SRTKT1631SS ada?", verdict(domain_hint="inventory", entities=[ht.asked("SRTKT1631SS")])),
    ("SRTKT1631SS 有货吗", verdict(domain_hint="inventory", entities=[ht.asked("SRTKT1631SS")])),
    ("delivery to hanlim", verdict(domain_hint="order", entities=[{**ht.asked("hanlim"), "hint": "customer"}])),
]


@pytest.mark.parametrize(
    "message,v", NOT_AN_ANSWER_PHRASINGS, ids=[p[0] for p in NOT_AN_ANSWER_PHRASINGS]
)
def test_not_an_answer_phrasings_leave_the_pick_unanswered(message, v):
    state = DymConsole()
    state.first_ask("check stock STWC2867")
    loaded = replace(state.state, turn_no=2)
    _applied, plan = apply(loaded, {**v, "open_question_answer": answer(None)}, build_policy())
    rules = plan.trace.rules_fired
    assert "answer_pending" not in rules
    assert not any(rule.startswith("open_question_answer_") for rule in rules)


def test_an_unusable_pick_falls_back_to_the_shape_rules():
    """A position off the list is no reading of the object at all: nothing is rewritten
    and the ordinary path decides (here: the same question asked again)."""
    console = _owner_dym()
    v = verdict(reference_positions=[7], open_question_answer=answer("pick", [item(7)]))
    console.say("7", v)
    assert "open_question_answer_pick" not in console.plans[-1].trace.rules_fired
    assert "answer_pending_unresolved" in console.plans[-1].trace.rules_fired
