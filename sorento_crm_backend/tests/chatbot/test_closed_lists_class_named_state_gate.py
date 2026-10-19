"""CLASS-NAMED-OFF-UNDER-STATE (architecture review F2, crew): "the message names its own class" is
CHAT-STATE's Subject to decide on the state path, so every class_named seam is a no-op when the
state gate is on (`ParserConfig.state_block`, head/parser.py; the engine then runs the state path and
`State.state_path` is set). State-off keeps today's rule; the R6-3 and HELD-OVER-NAMED-CLASS tests
stay as its guards.

Each test drives the input an existing state-off test uses for its seam, with the state gate ON and
the parser's state op `keep` (the Subject holds the product), and asserts the seam does not fire:

- seam 6, head/scheme_index.py `_asked_product_ids` (test_closed_lists_held_named_class "Shower span cert");
- seam 2, engine.py `scheme_index.names_own_class` before `scheme_without_product` (same input);
- seam 7, head/held_family.py `names_a_product` (held_named_class "sorento angle valve cert");
- seam 5, head/grounding.py `class_hint` (held_new_class "any zzbasin zzcabinet?");
- seam 4, turn/task.py the task-revise skip (held_new_class `_CLASS_ASK` with "6 pcs").

Seam 3, lanes/business/gate.py `names_class`, is not pinned: its branch needs a turn with NO entities
after the resolver, and the R6-3 input never gets there in either mode (measured on HEAD c9b339018a: the
gate reason is "ok" state-off and state-on, keep or new_subject, with or without stock, because the
described set's rows are the entities). `class_hint` is engine-only (stripped from the parse,
engine.py `_ENGINE_ENTITY_KEYS`) and set only by seam 5, so with seam 5 gated it cannot fire at all.

Seam 1 is `class_named.names_own_class` itself: its only callers are seams 2, 4, 6 and 7, which are
pinned here; a direct test would pin a gate argument that does not exist yet.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

import app.main  # noqa: F401  isort:skip
from app.services.ai_assistant_service import MCPRuntimeClient
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import trace as trace_mod
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _envelope, seeded, stub_access  # noqa: F401

KEEP = [{"op": "keep"}]


def _state(verdict: dict[str, Any], changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The verdict as a parser on the state path emits it (`state_changes`)."""
    return {**verdict, "state_changes": list(changes if changes is not None else KEEP)}


def _run(session_factory, stub_access, monkeypatch, turns, *, call_tool=None):
    """[(result, calls)] per turn with CLOSED LISTS and the state gate on; the apply records."""
    from tests.chatbot.test_closed_lists_scheme_held_none import _message

    def fake_resolve_config(db, *, current_date, override_version_id=None):
        return parser_mod.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=True,
            state_block=True,
        )

    queue = [verdict for _text, verdict in turns]
    monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls: list[tuple[str, dict]] = []

    def default_tool(self, name, args):
        calls.append((name, args))
        return json.dumps({"ok": True, "items": []})

    def recorded(self, name, args):
        calls.append((name, args))
        return call_tool(name, args)

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", recorded if call_tool else default_tool)
    traces: list = []
    real = trace_mod.TurnTrace.persisted
    monkeypatch.setattr(trace_mod.TurnTrace, "persisted", lambda self: (traces.append(real(self)) or traces[-1]))
    stub_access()
    out = []
    for n, (text, _verdict) in enumerate(turns):
        calls.clear()
        out.append((engine_mod.run_turn(_envelope(message=_message(text, n)), session_factory=session_factory), list(calls)))
    applied = [r for t in traces for r in t if r.get("kind") == "apply"]
    return out, applied


def _spy(monkeypatch, module, name: str) -> list:
    """Every (args, result) of `module.name` while the test runs."""
    seen: list = []
    real = getattr(module, name)

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        seen.append(out)
        return out

    monkeypatch.setattr(module, name, spy)
    return seen


# --- seams 6 and 2: the scheme over a named class (HELD-OVER-NAMED-CLASS input) ---------------


def _scheme_turns(session_factory, stub_access, monkeypatch, ids):
    from tests.chatbot.test_closed_lists_held_named_class import _ask, _category, _span_pick
    from tests.chatbot.test_closed_lists_scheme_held_none import _product, _stock

    return _run(
        session_factory, stub_access, monkeypatch,
        [("ZZWB1", _state(_stock(_product("ZZWB1")))), ("Shower span cert", _state(_ask(_category("shower"), _span_pick())))],
    )


def test_seam6_scheme_index_keeps_the_held_products_as_the_asked_ones_under_the_state_gate(
    session_factory, seeded, stub_access, monkeypatch
):
    """head/scheme_index.py `_asked_product_ids`: RED on HEAD, the class word empties the asked
    products, so `index_scheme` gives up (no note) and the held ZZWB1 is no longer the subject."""
    from app.services.chatbot.head import scheme_index
    from tests.chatbot.test_closed_lists_held_named_class import _seed

    ids = _seed(session_factory)
    notes = _spy(monkeypatch, scheme_index, "index_scheme")

    _scheme_turns(session_factory, stub_access, monkeypatch, ids)

    indexed = [note for _verdict, note in notes if note]
    assert indexed and "ZZWB1" in (indexed[-1].get("products") or []), notes


def test_seam2_the_engine_never_reads_the_scheme_without_its_held_product_under_the_state_gate(
    session_factory, seeded, stub_access, monkeypatch
):
    """engine.py `scheme_index.names_own_class(...)` before `scheme_without_product`: RED on HEAD, the
    named class sends the scheme's own certificates with the held product dropped. (Reached only when
    seam 6 fires: with seam 6 gated, `index_scheme` answers and this branch is not taken.)"""
    from app.services.chatbot.head import scheme_index
    from tests.chatbot.test_closed_lists_held_named_class import _seed

    ids = _seed(session_factory)
    notes = _spy(monkeypatch, scheme_index, "scheme_without_product")

    _scheme_turns(session_factory, stub_access, monkeypatch, ids)

    assert not [note for _verdict, note in notes if note], notes


# --- seam 7: held family narrowing with a brand over a named class ----------------------------


def test_seam7_held_family_narrows_the_held_product_under_the_state_gate(session_factory, seeded, stub_access, monkeypatch):
    """head/held_family.py `names_a_product = ... or names_own_class(said)`: RED on HEAD, the named
    class skips the held family narrowing (no note), so the brand never reads the held ZZCWB1."""
    from app.services.chatbot.head import held_family
    from tests.chatbot.test_closed_lists_held_named_class import _ask, _brand, _category, _kind_pick, _seed
    from tests.chatbot.test_closed_lists_scheme_held_none import _product, _stock

    _seed(session_factory)
    notes = _spy(monkeypatch, held_family, "narrow_held_family")

    _run(
        session_factory, stub_access, monkeypatch,
        [("ZZCWB1", _state(_stock(_product("ZZCWB1")))),
         ("sorento angle valve cert", _state(_ask(_brand(), _category("zyx angle valve"), _kind_pick())))],
    )

    assert [note for _verdict, note in notes if note], notes


# --- seam 5: a category grounding turns into a spec (R6-3 input) -------------------------------


def _furniture_turns(session_factory, stub_access, monkeypatch):
    from tests.chatbot._attach_world import entity
    from tests.chatbot.test_closed_lists_held_new_class import _furniture_world, _stock_parse

    _furniture_world(session_factory)
    held = _state(_stock_parse([entity("ZZBF100", "product", canonical="ZZBF100")]))
    named = _state(_stock_parse([entity("zzbasin zzcabinet", "category")]))
    return _run(session_factory, stub_access, monkeypatch, [("ZZBF100", held), ("any zzbasin zzcabinet?", named)])


def test_seam5_grounding_sets_no_class_hint_under_the_state_gate(session_factory, seeded, stub_access, monkeypatch):
    """head/grounding.py: the furniture_type spec grounding makes of the parser's category carries no
    `class_hint` on the state path. RED on HEAD: it carries class_hint "category"."""
    _out, applied = _furniture_turns(session_factory, stub_access, monkeypatch)

    entities = [e for e in (applied[-1].get("verdict") or {}).get("entities") or [] if isinstance(e, dict)]
    assert entities and not [e for e in entities if e.get("class_hint")], entities


# --- seam 4: the task-revise skip (R6-3 task-seam input) --------------------------------------


def test_seam4_a_quantity_in_a_class_ask_revises_the_held_check_under_the_state_gate():
    """turn/task.py: on the state path the Subject decides, so "6" in a class ask revises the
    answered one-product check as it does with the gate off. RED on HEAD: the class word skips it."""
    from app.services.chatbot.turn.apply import apply
    from tests.chatbot._turn_helpers import build_policy, verdict
    from tests.chatbot.test_closed_lists_held_new_class import _CLASS_ASK, _answered_ten, _revised

    state = dataclasses.replace(_answered_ten(), state_path=True, state_led="carry")
    v = verdict(
        entities=list(_CLASS_ASK), demand_qty=6, closed_lists=True,
        domain_in_message=False, entity_op="replace_combine", domain_hint="master_products", intent_hint="check_product",
        scope_intent="specific", message_type="business_query", continuation=False, topic_reset=False, match_mode="and",
    )

    _state2, plan = apply(state, v, build_policy())

    assert _revised(plan), plan.trace.rules_fired
