"""CHAT-STATE round 3, R3-C (red): a close that names something is not a cancel.

While the bot's question is owed ("How many units for each?"), the parser sends ONLY
`close_question`, yet the message names something of its own (a product, a spec;
`current_message` true). A lone close was read as a cancel, which cleared every product
including the named one, hit `refused_empty_subject` and replied generically with no
lookup. Members: es-3e53ca255a (a new code named), es-sa6d8a507a ("s trap ada?" over
held products with a quantities question owed). Driven through the engine seam; the
parser output is stubbed, the code executes.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.turn import task as task_mod
from app.services.chatbot.turn.state import Focus, focus_to_wire
from tests.chatbot._turn_helpers import entity
from tests.chatbot.test_chat_state_r3a_fetch_quantity import STOCK, _fetched, _seed_more, _spec
from tests.chatbot.test_chat_state_seam import Seam, _emit, _op, _product, seam  # noqa: F401
from tests.chatbot.test_engine import stub_access  # noqa: F401

SATRAP_FAMILY = ["SRTWC8354-SH", "SRTWC8354-SH-150", "SRTWC8354-SH-200", "SRTWC8354-SH-P",
                 "SRTWC8354-SH-UF", "SRTWC8354-SH-UF-150", "SRTWC8354-SH-UF-200", "SRTWC8354-SH-UF-P"]


def _owed(seam: Seam, held: list[str]) -> dict:
    """The State while "How many units for each?" is owed over `held`."""
    _seed_more(seam, [c for c in held if c not in seam.uuid_of])
    rows, slots = [], []
    for code in held:
        key = seam.uuid_of[code]
        rows.append({"raw": code, "canonical_code": code, "hint": "product", "uuid": key, "current_message": False})
        slots.append(task_mod.Slot(key, code, None))
    task = task_mod.Task(kind="stock_qty", domain="inventory", status=task_mod.OPEN, slots=tuple(slots))
    return {"focus": focus_to_wire(Focus(products=rows, domains=["inventory"], tasks=(task,))), "open_question": None}


def _close_only(*entities, **extra):
    return _emit(domain_hint="inventory", intent_hint="check_stock", entities=list(entities),
                 state_changes=[_op("close_question")], **extra)


def _named(code: str) -> dict:
    return _product(code) | {"current_message": True}


def _held_codes(seam: Seam) -> list[str]:
    return [p["canonical_code"] for p in seam.state["focus"]["products"]]


# --------------------------------------------------------------------------- #
# A: the message names a product of its own
# --------------------------------------------------------------------------- #

NAMED_PRODUCT = [
    ("es_3e53ca255a_en", "MBF97401-AL stock Available?", "MBF97401-AL", ["SRT1"]),
    ("bm", "MBF97401-AL ada stok tak?", "MBF97401-AL", ["SRTSC04-BL", "SRTSC05-GM"]),
    ("zh", "MBF97401-AL 有货吗", "MBF97401-AL", ["SRT391-GM"]),
    ("other_code_en", "check SRTWB1409 instead", "SRTWB1409", SATRAP_FAMILY[:3]),
    ("other_code_bm", "SRT93-BL pulak, ada?", "SRT93-BL", ["SRT1", "SRT391-GM"]),
]


@pytest.mark.parametrize("message,named,held", [c[1:] for c in NAMED_PRODUCT], ids=[c[0] for c in NAMED_PRODUCT])
def test_r3c_a_close_beside_a_named_product_makes_it_the_subject_and_looks_it_up(seam, message, named, held):
    prev = _owed(seam, held)
    _seed_more(seam, [named] if named not in seam.uuid_of else [])
    out = seam.say(message, _close_only(_named(named)), previous=prev)
    assert "refused_empty_subject" not in seam.rules_fired, seam.rules_fired
    assert _fetched(seam.turn_calls[-1]) == {seam.uuid_of[named]}, (seam.turn_calls[-1], seam.rules_fired)
    # no stale subject: the held products the message did not keep do not come back
    assert _held_codes(seam) == [named], _held_codes(seam)


# --------------------------------------------------------------------------- #
# B: the message names a spec over the held subject
# --------------------------------------------------------------------------- #

NAMED_SPEC = [
    ("es_sa6d8a507a_s_trap_bm", "s trap ada?", _spec("S trap", "trap_type", "s_trap"), SATRAP_FAMILY),
    ("en_stainless", "stainless steel", _spec("stainless steel", "material", "stainless_steel"),
     ["SRTSC04-BL", "SRTSC05-GM", "SRTSS8770-BL"]),
    ("en_grey", "want grey", _spec("grey", "colour", "grey"),
     ["SRT36525-GY", "SRTWB1409", "SRT93-BL", "SRTWT7449-BL"]),
    ("zh_p_trap", "要P trap的", _spec("P trap", "trap_type", "p_trap"), SATRAP_FAMILY[:4]),
    ("bm_putih", "ada yang putih?", _spec("putih", "colour", "white"), ["SRT1", "SRT391-GM"]),
]


@pytest.mark.parametrize("message,spec,held", [c[1:] for c in NAMED_SPEC], ids=[c[0] for c in NAMED_SPEC])
def test_r3c_a_close_beside_a_named_spec_keeps_the_held_subject_and_looks_it_up(seam, message, spec, held):
    prev = _owed(seam, held)
    out = seam.say(message, _close_only(spec | {"current_message": True}), previous=prev)
    assert "refused_empty_subject" not in seam.rules_fired, seam.rules_fired
    fetched = _fetched(seam.turn_calls[-1])
    assert fetched and fetched <= {seam.uuid_of[c] for c in held}, (seam.turn_calls[-1], seam.rules_fired)
    assert set(_held_codes(seam)) <= set(held) and _held_codes(seam), _held_codes(seam)


# --------------------------------------------------------------------------- #
# Guards: a true lone close that names nothing still cancels as today
# --------------------------------------------------------------------------- #

LONE_CLOSE = [("en_never_mind", "never mind"), ("en_ok_cancel", "ok cancel"), ("bm_tak_payah", "tak payah"), ("zh_suanle", "算了")]


@pytest.mark.parametrize("message", [c[1] for c in LONE_CLOSE], ids=[c[0] for c in LONE_CLOSE])
def test_r3c_guard_a_lone_close_that_names_nothing_still_cancels(seam, message):
    prev = _owed(seam, ["SRT1", "SRT391-GM"])
    out = seam.say(message, _emit(domain_hint=None, intent_hint=None, state_changes=[_op("close_question")]), previous=prev)
    assert STOCK not in [n for n, _ in seam.turn_calls[-1]], seam.turn_calls[-1]
    assert seam.state["open_question"] is None
    assert all(t.get("status") != "open" for t in (seam.state["focus"].get("tasks") or [])), seam.state["focus"].get("tasks")


# --------------------------------------------------------------------------- #
# Review round: B1 an open task whose products left the subject closes
# --------------------------------------------------------------------------- #

def _task_codes(seam: Seam) -> set[str]:
    return {
        s.get("code") or s.get("raw")
        for t in (seam.state["focus"].get("tasks") or []) if t.get("status") == "open"
        for s in (t.get("slots") or [])
    }


B1_CASES = [
    ("en_es_3e53ca255a", "MBF97401-AL stock Available?", "MBF97401-AL", ["SRT1", "SRT391-GM"]),
    ("bm", "MBF97401-AL ada stok tak?", "MBF97401-AL", ["SRT1", "SRT391-GM"]),
    ("zh", "MBF97401-AL 有货吗", "MBF97401-AL", ["SRT1", "SRT391-GM"]),
]


def _then_five(seam: Seam, named: str, held: list[str]) -> None:
    seam.say("5", _emit(domain_hint="inventory", intent_hint="check_stock", entities=[],
                        state_changes=[_op("answer")], demand_qty=5,
                        open_question_answer={"mode": "all", "picked": [], "items": [], "qty_for_all": 5}))
    fetched = _fetched(seam.turn_calls[-1])
    old = {seam.uuid_of[c] for c in held}
    assert not (fetched & old), ("old task products fetched", seam.turn_calls[-1], seam.rules_fired)
    assert not (set(_held_codes(seam)) & set(held)), _held_codes(seam)
    assert not (_task_codes(seam) & set(held)), _task_codes(seam)


@pytest.mark.parametrize("message,named,held", [c[1:] for c in B1_CASES], ids=[c[0] for c in B1_CASES])
def test_r3c_b1_close_beside_named_product_then_a_number_is_not_for_the_old_task(seam, message, named, held):
    prev = _owed(seam, held)
    _seed_more(seam, [named] if named not in seam.uuid_of else [])
    seam.say(message, _close_only(_named(named)), previous=prev)
    assert _fetched(seam.turn_calls[-1]) == {seam.uuid_of[named]}, seam.turn_calls[-1]
    _then_five(seam, named, held)


@pytest.mark.parametrize("message,named,held", [c[1:] for c in B1_CASES], ids=[c[0] for c in B1_CASES])
def test_r3c_b1_close_plus_set_product_then_a_number_is_not_for_the_old_task(seam, message, named, held):
    prev = _owed(seam, held)
    _seed_more(seam, [named] if named not in seam.uuid_of else [])
    v = _emit(domain_hint="inventory", intent_hint="check_stock", entities=[_named(named)],
              state_changes=[_op("close_question"), _op("set", "product")])
    seam.say(message, v, previous=prev)
    assert _fetched(seam.turn_calls[-1]) == {seam.uuid_of[named]}, seam.turn_calls[-1]
    _then_five(seam, named, held)


# --------------------------------------------------------------------------- #
# S1: `current_message` null is not "restated"; it names its own
# --------------------------------------------------------------------------- #

NULL_FLAG = [
    ("en", "MBF97401-AL stock Available?", "MBF97401-AL", ["SRT1", "SRT391-GM"]),
    ("bm", "SRT93-BL pulak, ada?", "SRT93-BL", ["SRTSC04-BL", "SRTSC05-GM"]),
]


@pytest.mark.parametrize("message,named,held", [c[1:] for c in NULL_FLAG], ids=[c[0] for c in NULL_FLAG])
def test_r3c_s1_a_null_current_message_with_a_lone_close_is_not_a_cancel(seam, message, named, held):
    prev = _owed(seam, held)
    _seed_more(seam, [named] if named not in seam.uuid_of else [])
    seam.say(message, _close_only(_product(named) | {"current_message": None}), previous=prev)
    assert "refused_empty_subject" not in seam.rules_fired, seam.rules_fired
    assert _fetched(seam.turn_calls[-1]) == {seam.uuid_of[named]}, (seam.turn_calls[-1], seam.rules_fired)


# --------------------------------------------------------------------------- #
# S2 guard: a held product only restated (current_message false) + lone close cancels
# --------------------------------------------------------------------------- #

RESTATED = [
    ("en", "forget it, SRT1", ["SRT1", "SRT391-GM"], "SRT1"),
    ("bm", "tak jadi, SRT391-GM", ["SRT1", "SRT391-GM"], "SRT391-GM"),
]


@pytest.mark.parametrize("message,held,restated", [c[1:] for c in RESTATED], ids=[c[0] for c in RESTATED])
def test_r3c_s2_guard_a_restated_held_product_with_a_lone_close_still_cancels(seam, message, held, restated):
    prev = _owed(seam, held)
    seam.say(message, _close_only(_product(restated) | {"current_message": False}), previous=prev)
    assert STOCK not in [n for n, _ in seam.turn_calls[-1]], seam.turn_calls[-1]
    assert seam.state["open_question"] is None
    assert all(t.get("status") != "open" for t in (seam.state["focus"].get("tasks") or [])), seam.state["focus"].get("tasks")
