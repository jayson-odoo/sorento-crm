"""combined4 resolution (#1761 + #1755 merged into #1772): the policy the three resolution fixes serve.

Under the CHAT-STATE gate (`State.state_gate`, written by `turn/chat_state.apply_changes`) round 6's typed
Subject decides: #1755's `class_named.names_own_class` seams (task class_ask in `turn/apply.py`, the state-off
class rule in `engine._held_for_the_seams`, and through it the scheme-without-product check) do NOT fire.
State OFF, #1755 behaves as on its own branch. #1755's R6-1b `spec_any_keys` (a bare size held as width OR
length) must survive the state path's typed rows. #1761's `code_lookup` reaches the candidate shortlist only
when its own gate is on.

Sections: (1) spy guards, gate on / off; (2) RED spec_any_keys through `chat_state._ROW_FIELDS`; (3) code_lookup.
Harnesses are the round 6 suites' own (`test_chat_state_r6_s3_ops_decide`, `test_chat_state_r6_subject`,
`test_closed_lists_held_new_class`, `test_code_lookup_engine`).
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

import app.main  # noqa: F401  isort:skip
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_chat_state_seam import _op
from tests.chatbot.test_closed_lists_scheme_index import (  # noqa: F401 - fixtures / helpers used by name
    CODE, _file_ask, _file_fetches, _scheme, _seed,
)
from tests.chatbot.test_chat_state_r6_s3_ops_decide import (  # noqa: F401
    _ent, _label_class, _stock_first, applied,
)
from tests.chatbot.test_engine import _envelope, _parser_output, seeded, stub_access  # noqa: F401


def test_the_c4res_tree_is_the_one_under_test():
    import app

    assert "sorento_crm-chat-state-c4res" in app.__file__, app.__file__


# =============================================================== 1. spies: Subject decides under the gate
class _Seams:
    """Counts the #1755 class seams and the scheme-without-product check at their real call sites."""

    def __init__(self, monkeypatch):
        from app.services.chatbot import class_named, engine as engine_mod
        from app.services.chatbot.head import scheme_index
        from app.services.chatbot.turn import chat_state

        self.names_own_class = 0
        self.scheme_without_product = 0
        self.held_products = 0
        self.held_calls: list[tuple[bool, list[dict]]] = []  # (state_in.subject is not None, result)

        def spy(owner, name, counter):
            real = getattr(owner, name)

            def wrapped(*a, **k):
                setattr(self, counter, getattr(self, counter) + 1)
                return real(*a, **k)

            monkeypatch.setattr(owner, name, wrapped)

        spy(class_named, "names_own_class", "names_own_class")
        spy(scheme_index, "scheme_without_product", "scheme_without_product")
        spy(chat_state, "held_products", "held_products")

        real_held = engine_mod._held_for_the_seams

        def held(state_in, verdict, *, for_family):
            out = real_held(state_in, verdict, for_family=for_family)
            self.held_calls.append((state_in.subject is not None, out))
            return out

        monkeypatch.setattr(engine_mod, "_held_for_the_seams", held)


def _two_turns(session_factory, stub_access, monkeypatch, ops, *, gate: bool, class_word="water closet"):
    """Turn 1 holds the seeded WC product; turn 2 says a class ("water closet" = a member of the held
    class) beside a listed scheme, so the held-family, scheme-index and scheme-without-product seams all read."""
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import parser as parser_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot.test_chat_state_r6_s3_ops_decide import _message

    ids = _seed(session_factory)
    _label_class(session_factory, ids, "Water Closet")
    ask = _file_ask(_ent(class_word, "category"), _scheme("zzpps", "ZZPPS"))
    if gate:
        ask["state_changes"] = ops
    turns = [(CODE, _stock_first() if gate else _off_first()), (f"zzpps certificate {class_word}", ask)]

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai", model="m",
                                       api_key="k", closed_lists=True, state_block=gate)

    queue = [v for _t, v in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(MCPRuntimeClient, "call_tool",
                        lambda self, name, args: calls.append((name, args)) or json.dumps({"ok": True, "items": []}))
    stub_access()
    engine_mod.run_turn(_envelope(message=_message(turns[0][0], 0)), session_factory=session_factory)
    seams = _Seams(monkeypatch)  # armed for turn 2 only
    calls.clear()
    engine_mod.run_turn(_envelope(message=_message(turns[1][0], 1)), session_factory=session_factory)
    return ids, seams, list(calls)


def _off_first():
    v = _stock_first()
    v.pop("state_changes", None)
    return v


@pytest.mark.parametrize("ops", [[_op("set", "category")], [_op("keep")], [_op("new_subject")]],
                         ids=["set-category", "keep", "new_subject"])
def test_guard_gate_on_the_task_class_seam_and_the_state_off_class_rule_never_fire(
    session_factory, seeded, stub_access, monkeypatch, applied, ops
):
    ids, seams, _calls = _two_turns(session_factory, stub_access, monkeypatch, ops, gate=True)
    assert len(applied) >= 2, "the state path did not run"
    assert seams.names_own_class == 0, "#1755 names_own_class fired under the state gate"
    assert seams.held_calls, "engine._held_for_the_seams never ran"
    assert all(on_state_path for on_state_path, _held in seams.held_calls), seams.held_calls
    assert seams.held_products >= 1, "the Subject's held_products was not what the seams read"


def test_guard_gate_on_a_refine_over_a_held_member_never_runs_scheme_without_product(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    ids, seams, calls = _two_turns(session_factory, stub_access, monkeypatch, [_op("set", "category")], gate=True)
    assert seams.scheme_without_product == 0, "the held product was ignored by the scheme-without-product check"
    assert seams.names_own_class == 0
    scheme_reads = [held for on_state_path, held in seams.held_calls if held]
    assert any(p.get("uuid") == ids["product"] for held in scheme_reads for p in held), (
        "the Subject's held member did not reach the scheme seam", seams.held_calls)


def test_guard_gate_off_the_class_rule_still_fires_on_a_class_named_held_ask(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    ids, seams, calls = _two_turns(session_factory, stub_access, monkeypatch, [], gate=False)
    assert not applied, "the state path ran with the gate off"
    assert seams.names_own_class >= 1, "#1755 names_own_class did not fire with the gate off (task class_ask)"
    assert seams.held_calls and all(not on_state_path for on_state_path, _h in seams.held_calls), seams.held_calls
    assert all(held == [] for _s, held in seams.held_calls), ("the state-off class rule kept a held product", seams.held_calls)
    assert seams.scheme_without_product >= 1, "no held product reached the scheme-without-product check"
    assert all(f.get("product_ids") != [ids["product"]] for f in _file_fetches(calls)), calls


def test_guard_apply_class_ask_follows_the_gate():
    from app.services.chatbot import class_named
    from app.services.chatbot.turn.apply import apply
    from tests.chatbot._turn_helpers import build_policy, verdict
    from tests.chatbot.test_closed_lists_held_new_class import _CLASS_ASK, _answered_ten, _revised

    seen: list[int] = []
    real = class_named.names_own_class

    def spy(entities):
        seen.append(1)
        return real(entities)

    def plan_for(gate: bool):
        v = verdict(entities=list(_CLASS_ASK), demand_qty=6, closed_lists=True, domain_hint="master_products",
                    intent_hint="check_product", scope_intent="specific", message_type="business_query")
        state = dataclasses.replace(_answered_ten(), state_gate=gate)
        return apply(state, v, build_policy())[1]

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(class_named, "names_own_class", spy)
        plan_for(True)
        assert not seen, "names_own_class ran under state_gate (apply.py class_ask)"
        off = plan_for(False)
        assert seen, "names_own_class did not run with the gate off"
        assert not _revised(off), off.trace.rules_fired
    finally:
        mp.undo()


# =============================================================== 2. RED: spec_any_keys survives the state path
BARE_SIZE_ROW = {
    # the row grounding makes for a bare "600mm" (head/grounding.py Spec.entity), as the focus keeps it
    "raw": "600mm", "hint": "specification", "canonical_code": "600", "current_message": False, "confident": True,
    "spec_key": "size", "spec_value": 600, "spec_unit": "mm", "spec_label": "Size", "spec_words": "600mm",
    "spec_known": [], "spec_any_keys": ["dim_width", "dim_length"],
}


def _held_bare_size(op):
    from app.services.chatbot.turn import chat_state
    from app.services.chatbot.turn.state import Focus, State
    from tests.chatbot.test_chat_state_apply import DOMAINS, KINDS

    focus = Focus(domains=["inventory"], extra={"specification": [dict(BARE_SIZE_ROW)]})
    out = chat_state.apply_changes(
        State(focus=focus, turn_no=3),
        {"state_changes": [op], "entities": [], "domain_hint": "inventory", "intent_hint": "check_stock"},
        open_question=None, domains=DOMAINS, kinds=KINDS + ["category", "product_type", "specification"], brands=[],
        positions_read_elsewhere=False,
    )
    assert out.valid is True, out.log
    return out


def test_red_a_held_bare_size_keeps_spec_any_keys_into_the_fetch_input():
    op = _op("keep")
    from app.services.chatbot.turn import chat_state

    out = _held_bare_size(op)
    subject = out.state.subject
    assert subject is not None and subject.provenance.get("spec") == "held", subject
    ents = chat_state.fetch_entities(subject, {"entities": []}, out.state.focus, unsettled_only=False)["entities"]
    held = [e for e in ents if e.get("hint") == "specification" and e.get("spec_key") == "size"]
    assert held, ("the held bare size did not ride the fetch input", ents)
    assert held[0].get("spec_any_keys") == ["dim_width", "dim_length"], held[0]


def test_red_the_typed_predicate_row_carries_spec_any_keys():
    out = _held_bare_size(_op("keep"))
    rows = out.state.subject.predicate.get("spec") or []
    assert rows and rows[0].get("spec_any_keys") == ["dim_width", "dim_length"], rows


def test_guard_the_focus_path_still_carries_spec_any_keys_state_off():
    """#1755's own state-off mapping (turn_runtime.focus_entities) keeps the key: what the state path must match."""
    from app.services.chatbot import turn_runtime
    from app.services.chatbot.turn.state import Focus

    ents, _ = turn_runtime.focus_entities(Focus(domains=["inventory"], extra={"specification": [dict(BARE_SIZE_ROW)]}))
    spec = [e for e in ents if e.get("hint") == "specification"]
    assert spec and spec[0].get("spec_any_keys") == ["dim_width", "dim_length"], ents


# =============================================================== 3. #1761 code_lookup kw only under its own gate
def _lookup_turn(session_factory, stub_access, monkeypatch, *, code_lookup: bool):
    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import candidates as candidates_mod
    from app.services.chatbot.head import parser as parser_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot.test_code_lookup_engine import MEANT, TYPED, _message, _seed as _seed_codes

    _seed_codes(session_factory)
    kws: list[Any] = []
    real = candidates_mod.shortlist

    def spy(*a, **k):
        kws.append(k.get("code_lookup"))
        return real(*a, **k)

    blocks: list[str] = []

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k",
                                       closed_lists=True, state_block=True, code_lookup=code_lookup)

    verdict = _parser_output(
        intent_hint="check_stock", domain_hint="inventory", user_goal="ask", state_changes=[_op("set", "product")],
        entities=[{"raw": TYPED, "hint": "product", "canonical_code": MEANT, "current_message": True, "confident": True}],
    )
    monkeypatch.setattr(candidates_mod, "shortlist", spy)
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: blocks.append(user_block) or verdict)
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: json.dumps({"ok": True, "items": []}))
    stub_access()
    engine_mod.run_turn(_envelope(message=_message(f"Check stock {TYPED}")), session_factory=session_factory)
    return kws, blocks[0]


def test_guard_code_lookup_kw_reaches_the_shortlist_and_the_parser_block_only_with_its_gate_on(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    kws, block = _lookup_turn(session_factory, stub_access, monkeypatch, code_lookup=True)
    assert applied, "state path did not run"
    assert kws and all(k is True for k in kws), kws
    assert "near code" in block, block


def test_guard_code_lookup_off_under_the_state_gate_passes_no_kw_and_no_near_line(
    session_factory, seeded, stub_access, monkeypatch, applied
):
    kws, block = _lookup_turn(session_factory, stub_access, monkeypatch, code_lookup=False)
    assert applied, "state path did not run"
    assert kws and not any(kws), kws
    assert "near code" not in block, block
