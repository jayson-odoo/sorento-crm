"""CHAT-STATE round 4 (red): the held product's family is its `family_code` siblings.

Real members (cp0 TRAIN follow-ups): cp0-665ba3e897 (SRTWC286-SH x10, "How about p trap"),
cp0-253d58ba8b (MWC6603-S8 x5, "If p trap?"), cp0-fcd44fe521 (CB94SS-BL x20, "I mean this got
chrome colour?"). Data: products share `family_code`, `variant_of_id` is NULL. A spec said about a
held product narrows that product's family and carries the held quantity onto each member; when no
sibling carries the value the reply says plainly there is none on record and the held subject
stays (crew ruling 18 Oct (2)(a)): never the catalogue's other products.
"""
from __future__ import annotations

import pytest

from tests.chatbot._family_code_seed import seed_rows
from tests.chatbot._turn_helpers import entity  # noqa: F401
from tests.chatbot.test_chat_state_r3a_fetch_quantity import _family_turn, _fetched, _reply, _wanted
from tests.chatbot.test_chat_state_seam import _op  # noqa: F401
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401

NONE_PHRASES = ("none on record", "tiada rekod", "没有记录")
TRAP_REG = ("trap_type", ["s_trap", "p_trap"], {"p_trap": ["p trap"], "s_trap": ["s trap"]})
COLOUR_REG = ("colour", ["black", "chrome"], {"chrome": ["chrome"], "black": ["black"]})


def _spec(raw, key, value):
    return {"raw": raw, "hint": "specification", "canonical_code": None, "spec_key": key, "spec_value": value,
            "current_message": True, "confident": True}


def _verdict(spec, domain="inventory", intent="check_stock"):
    return _parser_output(intent_hint=intent, domain_hint=domain, user_goal="spec of the held product",
                          entities=[spec], state_changes=[_op("keep")])


def _says_none(out) -> bool:
    return any(p in _reply(out) for p in NONE_PHRASES)


# Real SRTWC286 family_code siblings, plus catalogue P-traps of OTHER families (decoys).
SRTWC286_ROWS = [(c, "SRTWC286", "trap_type", "p_trap" if c.endswith("-P") and "PP" not in c else "s_trap")
                 for c in ["SRTWC286-SH", "SRTWC286-SH-150", "SRTWC286-SH-200", "SRTWC286-SH-NEW",
                           "SRTWC286-SH-NEW-150", "SRTWC286-SH-NEW-200", "SRTWC286-SH-NEW-P", "SRTWC286-SH-P",
                           "SRTWC286-SH-PP", "SRTWC286-SH-UF"]]
DECOYS = [("CWC7601-P-RL-NEW", "CWC7601", "trap_type", "p_trap"), ("SRTWC6022-SH-UF-NEW", "SRTWC6022", "trap_type", "p_trap"),
          ("MWC7601-RL-P", "MWC7601", "trap_type", "p_trap")]

P_TRAP_PHRASINGS = [
    ("en_how_about_p_trap", "How about p trap", "p trap"),
    ("bm_ada_p_trap", "ada p trap tak?", "p trap"),
    ("zh_p_trap", "有P trap的吗?", "p trap"),
]


@pytest.mark.parametrize("message,raw", [c[1:] for c in P_TRAP_PHRASINGS], ids=[c[0] for c in P_TRAP_PHRASINGS])
def test_r4_cp0_665ba3e897_p_trap_narrows_the_held_family_code_siblings_and_carries_the_quantity(
    session_factory, seeded, stub_access, monkeypatch, message, raw
):
    ids = seed_rows(session_factory, SRTWC286_ROWS + DECOYS, registry=TRAP_REG)
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, message, ids, "SRTWC286-SH", 10,
                              _verdict(_spec(raw, "trap_type", "p_trap")))
    landed = {ids["SRTWC286-SH-P"], ids["SRTWC286-SH-NEW-P"]}
    assert _fetched(calls) == landed, (calls, _reply(out))
    assert _wanted(calls) == {pid: 10 for pid in landed}, (calls, _reply(out))
    assert "how many" not in _reply(out)
    assert not (_fetched(calls) & {ids[c[0]] for c in DECOYS})


NONE_PHRASINGS_253 = [
    ("en_if_p_trap", "If p trap?"),
    ("bm_kalau_p_trap", "kalau p trap?"),
    ("zh_p_trap", "P trap的呢?"),
]


@pytest.mark.parametrize("message", [c[1] for c in NONE_PHRASINGS_253], ids=[c[0] for c in NONE_PHRASINGS_253])
def test_r4_cp0_253d58ba8b_no_sibling_carries_p_trap_says_none_on_record_and_keeps_the_held_product(
    session_factory, seeded, stub_access, monkeypatch, message
):
    rows = [("MWC6603-S8", "MWC6603", "trap_type", "s_trap")] + DECOYS
    ids = seed_rows(session_factory, rows, registry=TRAP_REG)
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, message, ids, "MWC6603-S8", 5,
                              _verdict(_spec("p trap", "trap_type", "p_trap")))
    assert _fetched(calls) <= {ids["MWC6603-S8"]}, (calls, _reply(out))
    assert not (_fetched(calls) & {ids[c[0]] for c in DECOYS})
    assert _says_none(out), _reply(out)
    assert "how many" not in _reply(out)
    assert "mwc6603-s8" in _reply(out), _reply(out)


NONE_PHRASINGS_FCD = [
    ("en_got_chrome", "I mean this got chrome colour?"),
    ("bm_ada_chrome", "maksud saya yang ada warna chrome?"),
    ("zh_chrome", "我是说这个有chrome颜色吗?"),
]


@pytest.mark.parametrize("message", [c[1] for c in NONE_PHRASINGS_FCD], ids=[c[0] for c in NONE_PHRASINGS_FCD])
def test_r4_cp0_fcd44fe521_spec_no_family_member_carries_keeps_the_held_subject_without_widening(
    session_factory, seeded, stub_access, monkeypatch, message
):
    rows = [("CB94SS-BL", "CB94SS", "colour", "black")] + [
        (c, f"CHR{n}", "colour", "chrome") for n, c in enumerate(["CH100-CR", "CH101-CR", "CH102-CR"])]
    ids = seed_rows(session_factory, rows, registry=COLOUR_REG, class_label="Mixer")
    out, calls = _family_turn(session_factory, stub_access, monkeypatch, message, ids, "CB94SS-BL", 20,
                              _verdict(_spec("chrome", "colour", "chrome"), domain="master_products", intent="check_product"))
    chrome = {ids[c] for c in ("CH100-CR", "CH101-CR", "CH102-CR")}
    seen = {pid for _n, a in calls for pid in (a.get("product_ids") or [])}
    assert not (seen & chrome), (calls, _reply(out))
    assert _says_none(out), _reply(out)
    assert "cb94ss-bl" in _reply(out), _reply(out)
    assert "chrome products" not in _reply(out)
