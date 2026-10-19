"""CHAT-STATE round 6, S1 (red): one typed `Subject`, written only by `chat_state.apply_changes`.

UAC AC-S1-1..AC-S1-6 (documentation/plans/chatbot/chat-state-subject-r6-acceptance-criteria.md).

The CONTRACT these tests hold the coder to (names are the contract):
  * `app.services.chatbot.turn.state.Subject`, a dataclass; `State.subject: Subject | None`
    (None until a state-led turn applied; `apply_changes` returns it on `Applied.state.subject`).
  * `Subject.source`      : "ids" | "predicate" | "unresolved".
  * `Subject.product_ids` : tuple[str, ...] of explicit product uuids (source "ids"), else ().
  * `Subject.predicate`   : dict axis -> list of TYPED ROWS, axes from {"brand", "class", "spec", "family"}.
                            A row is a dict `{"value": <word or code>, "key": <registry key or uuid>}`
                            (AC-S1-7: never a bare string, so the fetch never re-reads the focus).
                            "class" is ONE axis (category + product_type together); an absent
                            axis has no key.
  * `Subject.scope`       : frozenset of company ids; `Subject.hidden`: frozenset of hidden keys
                            (both default empty at the unit level, the engine fills them).
  * `Subject.provenance`  : dict axis -> "held" | "said" | "offer"; axes are the predicate axes
                            plus "product"; a cleared axis is ABSENT.
  * The engine's memory trace `state` log carries `"subject"`: the Subject as a JSON dict with the
    same field names (shadow log: no reply or fetch changes).
Only `turn/chat_state.py` constructs or assigns a Subject (AC-S1-2).
"""
from __future__ import annotations

import json
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
from tests.chatbot.test_chat_state_seam import Seam, _op, seam  # noqa: F401 - fixture used by name

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
    raw = [raw] if isinstance(raw, (str, dict)) else raw
    return {str(v.get("value") if isinstance(v, dict) else v).casefold() for v in raw}


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


# ----------------------------------------------------------------------- AC-S1-2 (AST)
ALLOWED = "app/services/chatbot/turn/chat_state.py"
_REPLACERS = {"replace", "dataclasses_replace"}


def _writes_subject(tree) -> list[int]:
    """Line numbers of: a `Subject(...)` call, a `subject=` keyword to a replace / dataclasses.replace
    / dataclasses_replace call, a `.subject =` assignment, a `setattr(x, "subject", ...)`. A plain local
    variable named subject matches none of these."""
    import ast

    def name(node):
        return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = name(node.func)
            if fn == "Subject":
                hits.append(node.lineno)
            elif fn in _REPLACERS | {"State"} and any(k.arg == "subject" for k in node.keywords):
                hits.append(node.lineno)
            elif fn == "setattr" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value == "subject":
                hits.append(node.lineno)
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            hits += [node.lineno for t in targets if isinstance(t, ast.Attribute) and t.attr == "subject"]
    return hits


def test_r6_s1_the_ast_check_ignores_a_plain_local_named_subject():
    import ast

    assert _writes_subject(ast.parse("subject = 1\nx = f(subject)\ndef g(subject): return subject")) == []
    assert len(_writes_subject(ast.parse("Subject()\nreplace(s, subject=1)\nx.subject = 2\nsetattr(x, 'subject', 1)\nState(focus=f, subject=s)"))) == 5


def test_r6_s1_only_the_applier_builds_or_assigns_the_subject():
    import ast

    root = Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"
    offenders, applier_builds = [], False
    for path in root.rglob("*.py"):
        rel = "app/services/chatbot/" + path.relative_to(root).as_posix()
        lines = _writes_subject(ast.parse(path.read_text()))
        if rel == ALLOWED:
            applier_builds = applier_builds or bool(lines)
        else:
            offenders += [f"{rel}:{n}" for n in lines]
    assert applier_builds, f"{ALLOWED} builds no Subject yet"
    assert not offenders, "Subject written outside the applier: " + ", ".join(offenders)


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


# ----------------------------------------------------------------------- S2: the fetch reads the Subject
def _spy_patches(monkeypatch):
    """Count the legacy carry patches under every name (AC-S2-4)."""
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.turn import chat_state

    seen: dict[str, int] = {"with_carried_entities": 0, "carried_entities_except": 0,
                            "carry_onto_family": 0, "narrow_held_to_brands": 0}

    def wrap(mod, name):
        real = getattr(mod, name)

        def spy(*a, **k):
            seen[name] += 1
            return real(*a, **k)

        monkeypatch.setattr(mod, name, spy)

    wrap(turn_runtime, "with_carried_entities")
    wrap(turn_runtime, "carried_entities_except")
    wrap(chat_state, "carry_onto_family")
    wrap(chat_state, "narrow_held_to_brands")
    return seen


def _f1_two_turns(chat, world, state_changes=True):
    brand = _brand_word(world, "sorento")
    chat.say(f"{brand} basins and water closets", _ask_with(
        [_entity(brand, "brand"), _entity("basin", "category"), _entity("water closet", "category")],
        [_op("set", "brand"), _op("set", "category")], "t1"))
    n = len(chat.calls)
    chat.say("toilets only", _ask_with([_entity("water closet", "category")],
                                       [_op("set", "category"), _op("close_question")], "t2"))
    return n


def _turn2_variants(world):
    wc = lambda: _entity("water closet", "category")  # noqa: E731
    code = world["close_couple"]["sorento"][0].product_code
    cabana = _brand_word(world, "cabana")
    return {
        "refine-set-class": ([wc()], [_op("set", "category")]),
        "keep-restating-a-typed-class": ([wc()], [_op("keep")]),
        "answer": ([wc()], [_op("answer")]),
        "new-subject-brand-and-class": ([_entity(cabana, "brand"), wc()], [_op("new_subject")]),
        "typed-product-code": ([_entity(code, "product")], [_op("set", "product")]),
    }


@pytest.mark.parametrize("variant", ["refine-set-class", "keep-restating-a-typed-class", "answer",
                                     "new-subject-brand-and-class", "typed-product-code"])
def test_r6_s2_no_legacy_carry_rule_runs_under_any_name_on_a_state_led_turn(tchat, world, monkeypatch, variant):
    brand = _brand_word(world, "sorento")
    tchat.say("t1", _ask_with([_entity(brand, "brand"), _entity("basin", "category"), _entity("water closet", "category")],
                              [_op("set", "brand"), _op("set", "category")], "t1"))
    seen = _spy_patches(monkeypatch)
    entities, ops = _turn2_variants(world)[variant]
    tchat.say("t2", _ask_with(entities, ops, "t2"))
    assert seen == {"with_carried_entities": 0, "carried_entities_except": 0,
                    "carry_onto_family": 0, "narrow_held_to_brands": 0}, (variant, seen)


def test_r6_s2_guard_state_off_still_calls_with_carried_entities(session_factory, monkeypatch, stub_parser, stub_access, world):
    from tests.chatbot.test_attribute_asks_round7 import _Leena

    plain = _Leena(session_factory, monkeypatch, stub_parser, stub_access, world)  # no state_block
    seen = _spy_patches(monkeypatch)
    brand = _brand_word(world, "sorento")
    plain.say(f"{brand} water closets", _ask_with(
        [_entity(brand, "brand"), _entity("water closet", "category")], None, "t1"))
    assert seen["with_carried_entities"] >= 1, seen


def test_r6_s2_the_fetch_input_is_exactly_what_the_subject_says(tchat, world):
    g = _groups(world)
    n = _f1_two_turns(tchat, world)
    subject = tchat.state_log().get("subject")
    assert subject and subject["source"] == "predicate", subject
    assert {x.casefold() for x in subject["predicate"]["brand"]} and "brand" in subject["predicate"], subject
    assert [x.casefold() for x in subject["predicate"]["class"]] == ["water closet"], subject
    ids = {pid for c in tchat.calls[n:] for pid in (c["args"].get("product_ids") or [])}
    by_id = {p.id: p.product_code for p in world["every"]}
    fetched = {by_id[i] for i in ids if i in by_id}
    assert fetched, tchat.calls[n:]
    assert fetched <= g["srt_wc"], ("the fetch holds more than the Subject (brand + class)", sorted(fetched - g["srt_wc"]))


# ----------------------------------------------------------------------- AC-S1-7: said under any op
@pytest.mark.parametrize("message", ["cabana water closets", "tandas duduk cabana", "cabana的马桶"])
def test_r6_s1_a_value_typed_this_message_is_said_under_new_subject_and_never_the_held_one(message):
    focus = Focus(brands=["SORENTO"], domains=["inventory"], extra={"category": [_row("Basin", "category")]})
    ents = [entity("cabana", "brand", canonical_code="CABANA"), entity("Water Closet", "category", canonical_code="WC")]
    s = _subject(_apply(focus, verdict(state_changes=[_op("new_subject")], entities=ents, user_goal=message)))
    assert _vals(s, "brand") == {"cabana"}, ("held Sorento kept beside the said Cabana", s.predicate)
    assert _vals(s, "class") == {"water closet"}, s.predicate
    assert s.provenance["brand"] == "said" and s.provenance["class"] == "said", s.provenance


def test_r6_s1_predicate_values_are_typed_rows_with_the_value_and_its_key():
    focus = Focus(brands=["SORENTO"], domains=["inventory"])
    ents = [entity("cabana", "brand", canonical_code="CABANA"), entity("Water Closet", "category", canonical_code="WC")]
    s = _subject(_apply(focus, verdict(state_changes=[_op("set", "brand"), _op("set", "category")], entities=ents)))
    for axis, key in (("brand", "CABANA"), ("class", "WC")):
        rows = s.predicate[axis]
        assert rows and all(isinstance(r, dict) for r in rows), (axis, rows)
        assert rows[0]["value"] and (rows[0].get("key") or rows[0].get("uuid")), (axis, rows)
        assert key in (rows[0].get("key"), rows[0].get("uuid")), (axis, rows)
    held = _subject(_apply(focus, verdict(state_changes=[_op("keep")])))
    assert all(isinstance(r, dict) and r.get("value") for r in held.predicate["brand"]), held.predicate


# ----------------------------------------------------------------------- AC-S1-8: settle after resolve
def test_r6_s1_a_typed_code_the_resolver_places_settles_the_final_subject_to_ids(tchat, world):
    brand = _brand_word(world, "sorento")
    tchat.say("t1", _ask_with([_entity(brand, "brand"), _entity("water closet", "category")],
                              [_op("set", "brand"), _op("set", "category")], "t1"))
    product = world["close_couple"]["sorento"][0]
    tchat.say(product.product_code, _ask_with([_entity(product.product_code, "product")], [_op("set", "product")], "t2"))
    s = tchat.state_log().get("subject")
    assert s and s["source"] == "ids" and str(product.id) in s["product_ids"], s
    assert {"brand", "class"} <= set(s["predicate"]), ("the held predicate was lost because a product was said", s)


def test_r6_s1_a_typed_token_the_resolver_cannot_place_settles_to_unresolved(tchat, world):
    brand = _brand_word(world, "sorento")
    tchat.say("t1", _ask_with([_entity(brand, "brand"), _entity("water closet", "category")],
                              [_op("set", "brand"), _op("set", "category")], "t1"))
    tchat.say("ZZ-9981", _ask_with([_entity("ZZ-9981", "product")], [_op("set", "product")], "t2"))
    s = tchat.state_log().get("subject")
    assert s and s["source"] == "unresolved", s


# ----------------------------------------------------------------------- AC-S2-5: R4-A answer pick
def test_r6_s2_an_answer_naming_an_offered_brand_is_offer_and_the_fetch_holds_that_brand_only(seam, monkeypatch):
    from tests.chatbot.test_chat_state_r4a_brand_offer import (
        DEFAULT_HELD_E9, _brand_pick, _held_state, _plans, _set_keys,
    )

    plans = _plans(monkeypatch)
    prev = _held_state(seam, DEFAULT_HELD_E9)
    key = prev["focus"]["set_page"]["set_key"]
    key.update({"brand": "Sorento", "brand_default": True})
    out = seam.say("cabana", _brand_pick("cabana", changes=[_op("answer")]), previous=prev)
    subject = seam.memory(out).get("state", {}).get("subject")
    assert subject and subject["provenance"].get("brand") == "offer", subject
    keys = _set_keys(plans)
    assert len(keys) == 1, (keys, seam.rules_fired)
    import json as _json

    blob = _json.dumps(keys[0], default=str).lower()
    assert "cabana" in blob and "sorento" not in blob, ("the held brand rides beside the offered one", keys[0])


# ----------------------------------------------------------------------- AC-S1-9 (card R1 / R4 / R5, lead decision)
def test_r6_s1_keep_restating_the_same_held_class_keeps_the_held_brand():
    focus = Focus(brands=["SORENTO"], domains=["inventory"], extra={"category": [_row("Water Closet", "category")]})
    s = _subject(_apply(focus, verdict(state_changes=[_op("keep")], entities=[_cat("Water Closet")])))
    assert _vals(s, "brand") == {"sorento"} and _vals(s, "class") == {"water closet"}, s.predicate
    assert s.provenance["brand"] == "held", s.provenance


def test_r6_s1_answer_naming_a_class_fills_only_the_asked_slot_and_keeps_the_brand():
    focus = Focus(brands=["SORENTO"], domains=["inventory"], extra={"category": [_row("Basin", "category")]})
    v = verdict(state_changes=[_op("answer")], entities=[_cat("Water Closet")])
    v["open_question_answer"] = {"mode": "value", "picked": [], "items": [], "qty_for_all": None}
    oq = {"kind": "class_pick", "options": [{"position": 1, "label": "Water Closet"}]}
    s = _subject(_apply(focus, v, open_question=oq))
    assert _vals(s, "class") == {"water closet"} and s.provenance["class"] == "said", s
    assert _vals(s, "brand") == {"sorento"} and s.provenance["brand"] == "held", s


def test_r6_s1_new_subject_naming_only_a_product_drops_the_held_brand():
    uid = "33333333-3333-3333-3333-333333333333"
    focus = Focus(brands=["SORENTO"], domains=["inventory"], extra={"category": [_row("Basin", "category")]})
    ent = entity("SRTWC286", "product", canonical_code="SRTWC286", uuid=uid)
    s = _subject(_apply(focus, verdict(state_changes=[_op("new_subject")], entities=[ent])))
    assert s.provenance.get("brand") != "held" and "brand" not in (s.predicate or {}), s
    assert "class" not in (s.predicate or {}), s


def test_r6_s1_a_rejected_change_set_leaves_the_held_subject_and_the_engine_does_not_crash(chat, world):
    g = _groups(world)
    brand = _brand_word(world, "sorento")
    chat.say("t1", _ask_with([_entity(brand, "brand"), _entity("water closet", "category")],
                             [_op("set", "brand"), _op("set", "category")], "t1"))
    # an unknown axis rejects the whole change set (`state_led` stays None on it); `say` asserts the turn is done
    t2 = chat.say("ok", _ask_with([], [_op("set", "no_such_axis")], "ok"))
    listed = _codes_in(t2, world)
    assert listed and listed <= g["srt_wc"], ("the held subject was not fetched after a rejected change set", t2[:200])


# ----------------------------------------------------------------------- AC-S1-10 held token without uuid
def _tokens(obj, code):
    """Rows (anywhere in the Subject) whose key is the held code."""
    out = []
    def walk(v):
        if isinstance(v, dict):
            if v.get("key") == code:
                out.append(v)
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(obj)
    return out


def test_r6_s1_a_held_product_without_a_uuid_stays_in_the_subject_as_a_token_keyed_by_its_code():
    import dataclasses

    row = {"raw": "SRTWC286-SH", "canonical_code": "SRTWC286-SH", "hint": "product", "current_message": False}
    s = _subject(_apply(Focus(products=[row], domains=["inventory"]), verdict(state_changes=[_op("keep")])))
    assert s.source != "unresolved", s
    assert _tokens(dataclasses.asdict(s), "SRTWC286-SH"), ("no token row keyed by the held code", s)


@pytest.mark.parametrize("message", ["any promo?", "ada promosi tak", "有促销吗"])
def test_r6_s1_a_keep_turn_over_a_held_code_with_no_uuid_fetches_that_product(seam, message):
    from tests.chatbot.test_chat_state_r3a_fetch_quantity import _seed_more
    from tests.chatbot.test_chat_state_r4a_brand_offer import _ids_in_calls
    from tests.chatbot.test_chat_state_seam import _emit

    code = "SRTWC286-SH"
    if code not in seam.uuid_of:
        _seed_more(seam, [code])
    row = {"raw": code, "canonical_code": code, "hint": "product", "current_message": False}
    from app.services.chatbot.turn.state import focus_to_wire

    prev = {"focus": focus_to_wire(Focus(products=[row], domains=["inventory"])), "open_question": None}
    seam.say(message, _emit(domain_hint="inventory", intent_hint="check_stock", entities=[],
                            state_changes=[_op("keep")]), previous=prev)
    ids = _ids_in_calls(seam.turn_calls[-1])
    assert ids == {seam.uuid_of[code]}, ("the held token did not reach the fetch (or an unscoped fetch ran)", seam.turn_calls[-1], seam.rules_fired)


# ----------------------------------------------------------------------- AC-S1-11 unplaced tokens
def test_r6_s1_two_said_codes_one_placed_one_not_settles_to_ids_with_the_other_unplaced(tchat, world):
    placed = world["close_couple"]["sorento"][0]
    tchat.say("two codes", _ask_with(
        [_entity(placed.product_code, "product"), _entity("ZZ-9981", "product")], [_op("set", "product")], "two codes"))
    s = tchat.state_log().get("subject")
    assert s and s["source"] == "ids" and str(placed.id) in s["product_ids"], s
    assert "zz-9981" in json.dumps(s.get("unplaced"), default=str).lower(), ("unplaced does not list the other token", s)
