"""CHAT-STATE round 6, S1 (red): one typed `Subject`, written only by `chat_state.apply_changes`.

UAC AC-S1-1..AC-S1-6 (documentation/plans/chatbot/chat-state-subject-r6-acceptance-criteria.md).

The CONTRACT these tests hold the coder to (names are the contract):
  * `app.services.chatbot.turn.state.Subject`, a dataclass; `State.subject: Subject | None`
    (None until a state-led turn applied; `apply_changes` returns it on `Applied.state.subject`).
  * `Subject.source`      : "ids" | "predicate" | "unresolved".
  * `Subject.product_ids` : tuple[str, ...] of explicit product uuids (source "ids"), else ().
  * `Subject.predicate`   : dict axis -> list[str], axes from {"brand", "class", "spec", "family"}.
                            "class" is ONE axis (category + product_type together); an absent
                            axis has no key. Values are the entity's code or raw word.
  * `Subject.scope`       : frozenset of company ids; `Subject.hidden`: frozenset of hidden keys
                            (both default empty at the unit level, the engine fills them).
  * `Subject.provenance`  : dict axis -> "held" | "said" | "offer"; axes are the predicate axes
                            plus "product"; a cleared axis is ABSENT.
  * The engine's memory trace `state` log carries `"subject"`: the Subject as a JSON dict with the
    same field names (shadow log: no reply or fetch changes).
Only `turn/chat_state.py` constructs or assigns a Subject (AC-S1-2).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.turn.state import Focus, State
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_chat_state_apply import DOMAINS, KINDS
from tests.chatbot.test_chat_state_r5_set_axis_keeps_held import (  # noqa: F401 - fixtures used by name
    StateChat,
    _ask_with,
    _codes_in,
    _groups,
    _spec,
    chat,
    r3world,
    r4world,
    stub_access,
    stub_parser,
    world,
)
from tests.chatbot.test_attribute_asks_round3 import _entity
from tests.chatbot.test_attribute_asks_round7 import _brand_word
from tests.chatbot.test_chat_state_seam import _op

BRANDS = ["SORENTO", "MOCHA", "CABANA"]


def _apply(focus: Focus, v: dict[str, Any], *, open_question=None):
    from app.services.chatbot.turn import chat_state

    out = chat_state.apply_changes(
        State(focus=focus, turn_no=3), v, open_question=open_question, domains=DOMAINS,
        kinds=KINDS + ["category", "product_type", "specification"], brands=BRANDS, positions_read_elsewhere=False,
    )
    assert out.valid is True, out.log
    return out


def _subject(out):
    subject = getattr(out.state, "subject", None)
    assert subject is not None, "the applied State carries no Subject (State.subject missing / not written)"
    return subject


def _vals(subject, axis: str) -> set[str]:
    raw = (getattr(subject, "predicate", None) or {}).get(axis) or []
    raw = [raw] if isinstance(raw, str) else raw
    return {str(v).casefold() for v in raw}


def _row(raw: str, hint: str, **extra) -> dict[str, Any]:
    return {"raw": raw, "canonical_code": None, "hint": hint, "current_message": False, "confident": True, **extra}


def _held_class_brand(class_hint="category", class_word="Basin") -> Focus:
    return Focus(brands=["SORENTO"], domains=["inventory"], extra={class_hint: [_row(class_word, class_hint)]})


def _cat(word: str, hint: str = "category") -> dict[str, Any]:
    return entity(word, hint, canonical_code=None)


# ----------------------------------------------------------------------- AC-S1-1 / AC-S1-3
# fresh paraphrases: EN / BM / ZH
SAID_CLASS = [("en", "toilets only"), ("bm", "tandas duduk sahaja"), ("zh", "只看马桶")]


@pytest.mark.parametrize("message", [m for _i, m in SAID_CLASS], ids=[i for i, _m in SAID_CLASS])
def test_r6_s1_a_class_the_op_set_is_said_and_the_untouched_brand_stays_held(message):
    out = _apply(_held_class_brand(), verdict(state_changes=[_op("set", "category")],
                                              entities=[_cat("Water Closet")], user_goal=message))
    s = _subject(out)
    assert s.source == "predicate", s
    assert _vals(s, "class") == {"water closet"}, s
    assert _vals(s, "brand") == {"sorento"}, s
    assert s.provenance["class"] == "said" and s.provenance["brand"] == "held", s.provenance
    assert not s.product_ids


def test_r6_s1_a_cleared_axis_is_absent_from_predicate_and_provenance():
    out = _apply(_held_class_brand(), verdict(state_changes=[_op("clear", "brand")]))
    s = _subject(out)
    assert "brand" not in (s.predicate or {}) and "brand" not in s.provenance, s
    assert s.provenance.get("class") == "held" and _vals(s, "class") == {"basin"}, s


def test_r6_s1_a_spec_the_op_set_joins_the_held_brand_and_class():
    focus = Focus(brands=["SORENTO"], domains=["inventory"], extra={"category": [_row("Water Closet", "category")]})
    spec = {**_cat("p trap", "specification"), "spec_key": "trap_type", "spec_value": "p_trap"}
    s = _subject(_apply(focus, verdict(state_changes=[_op("set", "specification")], entities=[spec])))
    assert s.source == "predicate" and "spec" in s.predicate, s
    assert s.provenance["spec"] == "said"
    assert s.provenance["brand"] == "held" and s.provenance["class"] == "held", s.provenance


def test_r6_s1_a_brand_taken_from_the_bots_offer_is_offer():
    focus = Focus(
        products=[_row("SRTWB1086", "product", uuid="11111111-1111-1111-1111-111111111111", canonical_code="SRTWB1086")],
        domains=["inventory"],
        set_page={"set_key": {"domain": "inventory", "other_brands": [{"brand": "Sorento", "count": 18}, {"brand": "Cabana", "count": 1}]}},
    )
    brand = entity("cabana", "brand", canonical_code="CABANA")
    out = _apply(focus, verdict(state_changes=[_op("set", "brand")], entities=[brand]))
    s = _subject(out)
    assert s.provenance.get("brand") == "offer", s.provenance


def test_r6_s1_explicit_held_product_ids_are_source_ids_and_held():
    uid = "22222222-2222-2222-2222-222222222222"
    focus = Focus(products=[_row("SRTWC286", "product", uuid=uid, canonical_code="SRTWC286")], domains=["inventory"])
    s = _subject(_apply(focus, verdict(state_changes=[_op("keep")])))
    assert s.source == "ids" and uid in s.product_ids, s
    assert s.provenance["product"] == "held"


def test_r6_s1_subject_carries_scope_and_hidden_keys_as_frozensets():
    s = _subject(_apply(_held_class_brand(), verdict(state_changes=[_op("keep")])))
    assert isinstance(s.scope, frozenset) and isinstance(s.hidden, frozenset), (s.scope, s.hidden)


# ----------------------------------------------------------------------- AC-S1-4
@pytest.mark.parametrize("held_hint,new_hint", [("product_type", "category"), ("category", "product_type")],
                         ids=["held-type-set-category", "held-category-set-type"])
def test_r6_s1_a_class_is_one_axis_across_category_and_product_type(held_hint, new_hint):
    focus = _held_class_brand(held_hint, "Basin")
    out = _apply(focus, verdict(state_changes=[_op("set", new_hint)], entities=[_cat("Water Closet", new_hint)]))
    s = _subject(out)
    assert _vals(s, "class") == {"water closet"}, ("the old class bucket survived", s.predicate)
    assert not {"category", "product_type"} & set(s.predicate) | ({"category", "product_type"} & set(s.provenance)), s


# ----------------------------------------------------------------------- AC-S1-5
def test_r6_s1_an_empty_subject_is_unresolved():
    focus = Focus(customers=[{"raw": "Customer X", "canonical_code": "C0001", "hint": "customer", "current_message": False}])
    s = _subject(_apply(focus, verdict(state_changes=[_op("keep")])))
    assert s.source == "unresolved", s
    assert not s.product_ids and not s.predicate


@pytest.mark.parametrize("token", ["ZZ-9981", "qq4410x", "ZZ 77"])
def test_r6_s1_a_said_product_token_nothing_resolved_is_unresolved(token):
    focus = _held_class_brand()
    out = _apply(focus, verdict(state_changes=[_op("set", "product")], entities=[entity(token, "product")]))
    assert _subject(out).source == "unresolved"


# ----------------------------------------------------------------------- AC-S1-2
ALLOWED = "app/services/chatbot/turn/chat_state.py"
# The type itself lives in turn/state.py; construction and assignment only in ALLOWED.
BUILDS = re.compile(r"(?<![\w.])Subject\(|\.subject\s*=(?!=)|\bsubject\s*=\s*(?:Subject|_subject)\b")


def test_r6_s1_only_the_applier_builds_or_assigns_the_subject():
    root = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
    offenders, applier_builds = [], False
    for path in root.rglob("*.py"):
        rel = "app/services/chatbot/" + path.relative_to(root).as_posix()
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if "class Subject" in code or not BUILDS.search(code):
                continue
            if rel == ALLOWED:
                applier_builds = True
            else:
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert applier_builds, f"{ALLOWED} builds no Subject yet"
    assert not offenders, "Subject written outside the applier:\n" + "\n".join(offenders)


# ----------------------------------------------------------------------- AC-S1-6
class TracedChat(StateChat):
    """Keeps the turn id of every turn so its memory trace can be read."""

    def say(self, text, verdict):
        self.turn_ids = getattr(self, "turn_ids", [])
        real = engine_mod.run_turn

        def spy(*a, **k):
            out = real(*a, **k)
            self.turn_ids.append(out.turn_id)
            return out

        engine_mod.run_turn = spy
        try:
            return super().say(text, verdict)
        finally:
            engine_mod.run_turn = real

    def state_log(self) -> dict[str, Any]:
        row = self.session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == self.turn_ids[-1]).first()
        events = [r for r in (row.trace or []) if r.get("kind") == "memory" and "state" in r]
        assert events, "no memory trace event with a state log"
        return events[-1]["state"]


@pytest.fixture()
def tchat(session_factory, monkeypatch, stub_parser, stub_access, world):
    return TracedChat(session_factory, monkeypatch, stub_parser, stub_access, world)


SET_ASKS = [("en", "sorento water closets"), ("bm", "tandas duduk sorento"), ("zh", "sorento的马桶")]


@pytest.mark.parametrize("message", [m for _i, m in SET_ASKS], ids=[i for i, _m in SET_ASKS])
def test_r6_s1_the_trace_shadow_logs_the_subject_and_the_fetch_is_today_s(tchat, world, message):
    g = _groups(world)
    brand = _brand_word(world, "sorento")
    text = tchat.say(message, _ask_with(
        [_entity(brand, "brand"), _entity("water closet", "category")],
        [_op("set", "brand"), _op("set", "category")], message))
    # today's fetch (pinned from the observed run): the held brand's water closets, no other brand
    listed = _codes_in(text, world)
    assert listed and listed <= g["srt_wc"], sorted(listed)
    assert not listed & (g["cabana_wc"] | g["mocha_wc"]), sorted(listed)
    subject = tchat.state_log().get("subject")
    assert isinstance(subject, dict), "the trace's state log carries no `subject` entry"
    assert subject["source"] in ("ids", "predicate", "unresolved")
    assert subject["source"] == "predicate", subject
    assert {"brand", "class"} <= set(subject["predicate"]), subject
    assert subject["provenance"]["brand"] == "said" and subject["provenance"]["class"] == "said", subject
