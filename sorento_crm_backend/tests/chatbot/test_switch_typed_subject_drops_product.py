"""CHAT-PICK-QTY-STATE (red): a domain switch that TYPES its own subject drops the held product.

Crew ruling (a): a domain switch whose message types its own subject of ANY subject kind (the
kinds of `turn.state.KIND_FIELD_MAP`: product, customer, warehouse, brand; `current_message` not
False) starts a new subject. The held products (and warehouse / extra / tier, the CHAT-STATE r8
rebuild) are dropped and the typed subject is written back. A truly BARE switch (`switch_domain`,
nothing typed) keeps the held subject (CHAT-STATE r8, unchanged). The parser's echo of a held row
(`current_message` false) names nothing. Tier is NOT a subject kind: a typed tier over an open
tier_pick menu stays that menu's answer.

Measured on a dev copy, state path (masked): turn 1 held SRTWC6031-SH-UF (master_products);
turn 2 "Delivery for <customer>" [switch_domain, set customer], a typed customer with no code,
`domain_in_message` true, `entity_op` replace_combine, was filed `refine`
(`refinement_keeps_subject`) and the product stayed held; the fetch after the customer pick ran
with that product. The old path (no `state_changes`, the v63 shape) already files the same message
NEW_ASK (`decide.py`'s domain_in_message row) and drops the product: pinned here as a guard.

Levels: `chat_state.apply_changes` (pure), `turn.apply.apply` (the decision and the open-pick
reading), and `engine.run_turn` through the CHAT-STATE seam harness (`test_chat_state_seam.Seam`:
a dry-run emission, the state path on exactly when it carries `state_changes`).

Fake customers only ("ZZT Lim ..."); product codes are catalogue codes.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn import question as question_mod
from app.services.chatbot.turn.apply import apply
from app.services.chatbot.turn.pending import ask
from app.services.chatbot.turn.state import Focus, State, focus_to_wire
from tests.chatbot._turn_helpers import build_policy, entity, verdict
from tests.chatbot.test_chat_state_seam import (  # noqa: F401 - `seam` is a fixture used by name
    COMPANY_A, Seam, _as_office_staff, _emit, _op, seam,
)
from tests.chatbot.test_engine import stub_access  # noqa: F401 - fixture used by name

DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion", "master_products"]
KINDS = ["product", "customer", "brand", "warehouse", "tier", "order", "specification", "category"]
BRANDS = ["SORENTO", "SRT"]
HELD = "SRTWC6031-SH-UF"
TYPED = "zzt lim"
TRADING = "ZZT Lim Trading Sdn Bhd"
HARDWARE = "ZZT Lim Hardware Sdn Bhd"


# --------------------------------------------------------------------------- builders
def _held_row(code: str = HELD) -> dict[str, Any]:
    return {"raw": code, "canonical_code": code, "hint": "product", "uuid": f"u-{code}", "current_message": False}


def _held_customer() -> dict[str, Any]:
    return {"raw": TRADING, "canonical_code": "ZZT-C0001", "hint": "customer", "uuid": "u-ZZT-C0001",
            "current_message": False}


def _held_focus(**over: Any) -> Focus:
    """Turn 1's focus: "seat cover for srtwc6031-sh-uf" held one product, in master_products."""
    base: dict[str, Any] = {"products": [_held_row()], "domains": ["master_products"]}
    base.update(over)
    return Focus(**base)


def _typed(raw: str, hint: str, *, current_message: bool = True, code: str | None = None) -> dict[str, Any]:
    """A parser entity with the measured shape: a typed customer carries NO canonical code."""
    return {**entity(raw, hint, current_message=current_message), "canonical_code": code}


def _switch(domain: str, ents: list[dict[str, Any]], ops: list[dict[str, Any]] | None, **over: Any) -> dict[str, Any]:
    """A message that names its own domain (the parser's `domain_in_message`), no backward reference.
    `ops` None is the old path: the verdict carries no `state_changes` at all (v63 shape)."""
    v = verdict(domain_hint=domain, intent_hint=None, domain_in_message=True, entity_op="replace_combine",
                topic_reset=False, entities=ents, **over)
    if ops is not None:
        v["state_changes"] = ops
    return v


def _delivery_for(*, ops: list[dict[str, Any]] | None, current_message: bool = True, **over: Any) -> dict[str, Any]:
    """"Delivery for <customer>" as measured."""
    return _switch("order", [_typed(TYPED, "customer", current_message=current_message)], ops, **over)


def _apply(focus: Focus, v: dict[str, Any], **kw: Any):
    out = chat_state.apply_changes(
        State(focus=focus, turn_no=3), v, open_question=kw.pop("open_question", None), domains=DOMAINS,
        kinds=KINDS, brands=BRANDS, positions_read_elsewhere=False,
    )
    assert out.valid is True, out.log.get("rejected")
    return out


def _products(focus: Focus) -> list[Any]:
    return [p.get("canonical_code") for p in focus.products if isinstance(p, dict)]


def _subject_products(out) -> list[str]:
    s = out.state.subject
    return sorted([*(t["value"] for t in s.product_tokens), *s.product_ids])


def _typed_back(out, hint: str) -> list[Any]:
    """What this message typed of `hint`, as the applied verdict hands it to the kind rules."""
    return [e.get("raw") for e in out.verdict.get("entities") or []
            if e.get("hint") == hint and e.get("current_message") is not False]


SWITCH_SET_CUSTOMER = [_op("switch_domain"), _op("set", "customer")]


# --------------------------------------------------------------------------- 1. apply_changes (RED)
def test_1_a_switch_typing_a_customer_drops_the_held_product_and_leads_new_ask():
    out = _apply(_held_focus(), _delivery_for(ops=list(SWITCH_SET_CUSTOMER)))
    assert _products(out.state.focus) == [], (
        f"the held product rode a switch that typed its own customer: {_products(out.state.focus)}"
    )
    assert _subject_products(out) == [], f"the Subject still holds the held product: {_subject_products(out)}"
    assert out.state.state_led == "new_ask", f"led {out.state.state_led!r}, the ruling says new_ask (not refine)"
    assert _typed_back(out, "customer") == [TYPED], "the typed customer must be written back"
    assert list(out.state.focus.domains) == ["order"], out.state.focus.domains


def test_1_apply_files_the_typed_customer_switch_as_a_new_ask_not_a_refine():
    a = _apply(_held_focus(), _delivery_for(ops=list(SWITCH_SET_CUSTOMER)))
    new_state, plan = apply(a.state, a.verdict, build_policy())
    fired = plan.trace.rules_fired
    assert "refinement_keeps_subject" not in fired, fired
    assert (plan.trace.decision or {}).get("kind") == "new_ask", plan.trace.decision
    assert _products(new_state.focus) == [], f"the held product is still the subject: {_products(new_state.focus)}"
    assert TYPED in [c.get("raw") for c in new_state.focus.customers], new_state.focus.customers


# --------------------------------------------------------------------------- 2. engine, both paths
def _seed_held_product(session_factory) -> str:
    """The measured product, seeded under its own category so the harness family is untouched."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    db = session_factory()
    db.info["company_scope"] = frozenset({COMPANY_A})
    tag = uuid.uuid4().hex[:6]
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"ZZTC-cpqs-{tag}", category_name="ZZT seat cover",
                          class_label="seat cover", search_synonyms=[])
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"ZZTU-cpqs-{tag}", uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    pid = str(uuid.uuid4())
    db.add(Product(id=pid, product_code=HELD, product_name=f"ZZT {HELD}", category_id=cat.id, base_uom_id=uom.id,
                   list_price=1))
    db.commit()
    return pid


def _seed_customer(seam: Seam, name: str) -> str:
    from app.models.order import Customer

    db = seam.session_factory()
    db.info["company_scope"] = frozenset({COMPANY_A})
    row = Customer(id=str(uuid.uuid4()), customer_code=f"ZZT-{uuid.uuid4().hex[:8]}", customer_name=name,
                   company_id=COMPANY_A)
    db.add(row)
    db.commit()
    return row.id


def _held_session(pid: str) -> dict[str, Any]:
    row = {"raw": HELD, "canonical_code": HELD, "uuid": pid, "hint": "product", "current_message": False}
    return {"focus": focus_to_wire(Focus(products=[row], domains=["master_products"])), "open_question": None}


def _engine_turns(state_path: bool) -> list[tuple[str, dict[str, Any]]]:
    def ops(*o: dict[str, Any]) -> dict[str, Any]:
        return {"state_changes": list(o)} if state_path else {}

    pick = {"mode": "pick", "picked": [1], "items": [], "qty_for_all": None}
    customer = _typed(TYPED, "customer")
    return [
        ("Delivery for zzt lim", _emit(domain_hint="order", intent_hint=None, domain_in_message=True,
                                       entity_op="replace_combine", topic_reset=False, entities=[customer],
                                       **ops(*SWITCH_SET_CUSTOMER))),
        ("1", _emit(domain_hint="order", intent_hint=None, domain_in_message=False, entity_op="reuse",
                    reference_positions=[1], open_question_answer=pick, **ops(_op("pick", position=1)))),
        # The DO list asks which period first (DO-ASK-SIMPLIFY); the answer runs the fetch.
        ("this month", _emit(domain_hint="order", intent_hint=None, domain_in_message=False, entity_op="reuse",
                             date_mode="range", date_filter_start="2026-10-01", date_filter_end="2026-10-23",
                             **ops(_op("set", "period")))),
    ]


@pytest.mark.parametrize("path", ["state", "old"], ids=["state-path", "old-path-guard"])
def test_2_engine_after_the_customer_pick_the_fetch_carries_no_held_product(seam, path):
    """Red on the state path; the old path (no state_changes) is the green guard."""
    _as_office_staff(seam)
    pid = _seed_held_product(seam.session_factory)
    seeded = {_seed_customer(seam, TRADING), _seed_customer(seam, HARDWARE)}
    seam.state = _held_session(pid)
    switch, pick, period = _engine_turns(path == "state")

    seam.say(*switch)
    roster = seam.state.get("open_question") or {}
    assert roster.get("kind") == "customer_pick", ("harness: the typed customer must offer the customer roster", roster)
    # The two names tie on similarity, so the roster's own option 1 is the picked customer.
    picked = next(o.get("uuid") for o in roster.get("options") or [] if o.get("position") == 1)
    assert picked in seeded, roster
    after_switch = [p.get("canonical_code") for p in seam.state["focus"]["products"]]
    switch_rules = list(seam.rules_fired)
    seam.say(*pick)
    seam.say(*period)
    fetches = [(n, a) for n, a in seam.turn_calls[-1] if n.startswith("crm_")]
    assert fetches, "harness: the period answer ran no fetch"
    assert any(picked in (a.get("customer_ids") or []) for _n, a in fetches), (
        "harness: the fetch is not for the picked customer", fetches)

    blob = json.dumps(seam.turn_calls[-1], default=str)
    assert pid not in blob and HELD not in blob, (
        f"the held product rode the delivery fetch after the customer pick ({path}); held after the switch "
        f"{after_switch}, switch rules {switch_rules}; fetch {fetches}"
    )
    assert after_switch == [], f"the switch kept the held product on the stored focus: {after_switch}"


# --------------------------------------------------------------------------- 3. warehouse (RED) / brand (guard)
def test_3_a_switch_typing_a_warehouse_drops_the_held_product():
    """"stock at frg" over the held product: a typed warehouse is a subject of its own."""
    v = _switch("inventory", [_typed("frg", "warehouse", code="FRG")], [_op("switch_domain"), _op("set", "warehouse")])
    out = _apply(_held_focus(), v)
    assert _products(out.state.focus) == [], f"the held product rode a warehouse-typed switch: {_products(out.state.focus)}"
    assert _subject_products(out) == [], _subject_products(out)
    assert out.state.state_led == "new_ask", out.state.state_led
    assert _typed_back(out, "warehouse") == ["frg"], "the typed warehouse must be written back"


def test_3_guard_a_switch_typing_a_brand_is_already_a_new_subject():
    v = _switch("promotion", [_typed("srt", "brand", code="SRT")], [_op("switch_domain"), _op("set", "brand")],
                contains_flyer=True)
    out = _apply(_held_focus(), v)
    assert _products(out.state.focus) == [], _products(out.state.focus)
    assert _subject_products(out) == [], _subject_products(out)
    assert out.state.state_led == "new_ask", out.state.state_led


# --------------------------------------------------------------------------- 4. bare switch (guard, r8)
def test_4_guard_a_bare_switch_keeps_the_held_product():
    """"any orders?": a domain word, nothing typed."""
    out = _apply(_held_focus(), _switch("order", [], [_op("switch_domain")]))
    assert _products(out.state.focus) == [HELD], _products(out.state.focus)
    assert _subject_products(out) == [f"u-{HELD}"], _subject_products(out)
    assert out.state.state_led != "new_ask", out.state.state_led


# --------------------------------------------------------------------------- 5. echo (guard)
def test_5_guard_a_switch_whose_customer_is_the_parsers_echo_keeps_the_held_product():
    focus = _held_focus(customers=[_held_customer()])
    echo = _typed(TRADING, "customer", current_message=False, code="ZZT-C0001")
    out = _apply(focus, _switch("order", [echo], [_op("switch_domain")]))
    assert _products(out.state.focus) == [HELD], _products(out.state.focus)
    assert _subject_products(out) == [f"u-{HELD}"], _subject_products(out)
    assert out.state.state_led != "new_ask", out.state.state_led


# --------------------------------------------------------------------------- 6. open tier_pick menu
def _tier_menu() -> State:
    pending = ask(
        "tier_pick",
        [{"position": i, "label": t.replace("_", " "), "code": t, "uuid": t, "uuids": [t], "entity_type": "tier",
          "payload": {"tier": t}} for i, t in enumerate(["dealer", "office", "end_user"], 1)],
        asked_at_turn=2, expects="pick", payload={"domain": "promotion", "domains": ["promotion"]},
    )
    return State(focus=Focus(brands=["SORENTO"], domains=["promotion"]), pending=pending, turn_no=3)


def _menu_pick(ents: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    return verdict(domain_hint="promotion", entities=ents, reference_positions=[1],
                   open_question_answer={"mode": "pick", "picked": [1], "items": [], "qty_for_all": None}, **over)


def test_6_guard_a_typed_tier_over_the_open_tier_menu_stays_its_answer():
    _state, plan = apply(_tier_menu(), _menu_pick([_typed("dealer", "tier", code="dealer")],
                                                  access_levels=["dealer"]), build_policy())
    fired = plan.trace.rules_fired
    assert "open_question_answer_pick" in fired, fired
    assert "open_question_pick_fresh_ask" not in fired, fired


def test_6_a_typed_customer_over_the_open_tier_menu_is_a_fresh_ask():
    _state, plan = apply(_tier_menu(), _menu_pick([_typed(TYPED, "customer")]), build_policy())
    fired = plan.trace.rules_fired
    assert "open_question_pick_fresh_ask" in fired, f"the stale menu position answered a typed customer: {fired}"
    assert "open_question_answer_pick" not in fired, fired


# --------------------------------------------------------------------------- 7. old path (guards)
def _old_path(v: dict[str, Any]):
    assert "state_changes" not in v
    return apply(State(focus=_held_focus(), turn_no=3), v, build_policy())


def test_7_guard_old_path_a_typed_customer_with_its_own_domain_drops_the_held_product():
    new_state, plan = _old_path(_delivery_for(ops=None))
    assert (plan.trace.decision or {}).get("kind") == "new_ask", plan.trace.decision
    assert "new_ask_drops_product" in plan.trace.rules_fired, plan.trace.rules_fired
    assert _products(new_state.focus) == [], _products(new_state.focus)


def test_7_guard_old_path_with_a_backward_reference_refines_and_keeps_the_held_product():
    """"Delivery for <customer> for this one": the pronoun points at the held product."""
    new_state, plan = _old_path(_delivery_for(ops=None, anaphora={"backward_reference": True}))
    assert (plan.trace.decision or {}).get("kind") == "refine", plan.trace.decision
    assert "refinement_keeps_subject" in plan.trace.rules_fired, plan.trace.rules_fired
    assert _products(new_state.focus) == [HELD], _products(new_state.focus)


# --------------------------------------------------------------------------- 8. a pick never rebuilds (guard)
def test_8_guard_a_customer_roster_pick_with_a_switch_and_its_typed_name_never_rebuilds():
    """r8 review B2 pins a product roster; this is the customer roster, whose typed name the
    widened rule now counts as naming a subject: the pick answers the open question all the same."""
    from app.services.chatbot.turn.tail import last_list_after

    options = [{"position": i, "label": name, "code": f"ZZT-C000{i}", "name": name, "entity_type": "customer",
                "payload": {}} for i, name in enumerate([TRADING, HARDWARE], 1)]
    pending = ask("customer_pick", options, asked_at_turn=2, payload={"domain": "order"})
    ll = last_list_after(None, question=pending, sections=[], turn_no=2)
    st = State(focus=Focus(products=[_held_row()], domains=["order"], last_list=ll, tier=["dealer"]),
               pending=pending, turn_no=3, state_path=True)
    v = _switch("sales", [_typed(TRADING, "customer")], [_op("pick", position=1), _op("switch_domain")],
                reference_positions=[1])
    a = chat_state.apply_changes(st, v, open_question=question_mod.of_pending(pending), domains=DOMAINS,
                                 kinds=KINDS, brands=BRANDS, positions_read_elsewhere=False)
    assert a.valid is True, a.log.get("rejected")
    assert a.state.state_led == "answer", a.state.state_led
    assert a.state.pending is not None, "the open roster was wiped before it was answered"
    assert a.state.focus.tier == ["dealer"], f"the tier was rebuilt away: {a.state.focus.tier}"
    assert _products(a.state.focus) == [HELD], f"a pick rebuilt the subject: {_products(a.state.focus)}"
    _s, plan = apply(a.state, a.verdict, build_policy())
    assert "open_question_answer_pick" in plan.trace.rules_fired, plan.trace.rules_fired
