"""CHAT-STATE round 8 CARRY (red): a message that names its own subject drops every unrestated
held axis; `switch_domain` == `new_subject` (UAC chat-state-carry-r8-acceptance-criteria.md AC-R8-1..8).

Rule: a message that names its own subject (a typed or `set` product or brand) on a switch (the
`switch_domain` op or an implicit domain change) or on `new_subject` keeps products / warehouse /
extra / tier only if restated this turn; customers, brands, period, tasks, last_list keep their
current rules. A bare switch (nothing named) keeps the held subject whole. A spec over held
products stays the round 6 membership refine. Turn shapes are masked (codes only).

Pure level: `chat_state.apply_changes` on a held State. Seams the coder adds are guarded so a
missing one fails as an assertion: `chat_state.names_own_subject(verdict)`.
"""
from __future__ import annotations

import copy

import pytest

from app.services.chatbot.turn import chat_state
from app.services.chatbot.turn.state import Focus, State
from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_chat_state_apply import _op
from tests.chatbot.test_engine import stub_access  # noqa: F401 - fixture used by name

DOMAINS = ["inventory", "incoming", "order", "sales", "product_attachment", "promotion"]
KINDS = ["product", "customer", "brand", "warehouse", "tier", "order", "specification", "category"]
BRANDS = ["SORENTO", "SRT"]
BASINS = ["SRTWB1096-RG", "SRTWB1160-RG", "SRTWB248-RG"]
X = "SRTWB1096-RG"
Y = "SRTWC286-SH"


def _held(code, **extra):
    return {"raw": code, "canonical_code": code, "hint": "product", "uuid": f"u-{code}", "current_message": False, **extra}


def _focus(codes=BASINS, *, warehouse=True, tier=True, extra=True, domains=("inventory",)):
    return Focus(
        products=[_held(c) for c in codes],
        customers=[{"raw": "Cust A", "canonical_code": "C0001", "hint": "customer", "current_message": False}],
        warehouse=[{"raw": "frg", "hint": "warehouse", "current_message": False}] if warehouse else [],
        tier=["dealer"] if tier else [],
        extra={"order": [{"raw": "SO0001", "hint": "order", "current_message": False}]} if extra else {},
        brands=["SORENTO"],
        domains=list(domains),
    )


def _apply(focus, v):
    out = chat_state.apply_changes(
        State(focus=focus, turn_no=3), v, open_question=None, domains=DOMAINS, kinds=KINDS,
        brands=BRANDS, positions_read_elsewhere=False,
    )
    assert out.valid is True, out.log.get("rejected")
    return out


def _shape(out):
    f = out.state.focus
    return {
        "products": [p.get("canonical_code") for p in f.products],
        "warehouse": list(f.warehouse),
        "extra": {k: v for k, v in (f.extra or {}).items() if v},
        "tier": list(f.tier),
        "brands": list(f.brands),
        "customers": [c.get("canonical_code") for c in f.customers],
    }


def _subject_codes(out):
    s = out.state.subject
    return sorted([*(t["value"] for t in s.product_tokens), *s.product_ids])


def _brand(raw="srt", code="SRT"):
    return entity(raw, "brand", canonical_code=code)


def _product(code):
    return entity(code, "product", canonical_code=code)


def _carry_ops(op, *more):
    """The op under test (`switch_domain` or `new_subject`) beside the rest of the message's ops."""
    return [_op(op), *more]


def _seam_exists():
    assert hasattr(chat_state, "names_own_subject"), "chat_state.names_own_subject (the agreed seam) is missing"


SWITCH_OPS = ["switch_domain", "new_subject"]


# ---------------------------------------------------------------- AC-R8-1 (owner T8)
@pytest.mark.parametrize("op", SWITCH_OPS)
def test_r8_1_a_brand_named_switch_drops_held_products_and_warehouse(op):
    v = verdict(domain_hint="product_attachment", contains_flyer=True, entities=[_brand()])
    out = _apply(_focus(), verdict_with(v, _carry_ops(op, _op("set", "brand"))))
    shape = _shape(out)
    assert shape["products"] == [], f"held basins rode a brand-named {op}: {shape['products']}"
    assert shape["warehouse"] == [], f"held warehouse rode a brand-named {op}: {shape['warehouse']}"
    assert _subject_codes(out) == [], f"the Subject still holds {_subject_codes(out)}"


def verdict_with(v, ops):
    return {**v, "state_changes": ops}


@pytest.mark.parametrize("op", SWITCH_OPS)
def test_r8_1_held_family_does_not_run_on_a_new_subject(op):
    """held_family reads the products `_held_for_the_seams` hands it; none on a new subject."""
    from app.services.chatbot import engine

    v = verdict(domain_hint="product_attachment", contains_flyer=True, entities=[_brand()])
    out = _apply(_focus(), verdict_with(v, _carry_ops(op, _op("set", "brand"))))
    assert engine._held_for_the_seams(out.state, out.verdict, for_family=True) == [], "held_family would run on a held basin"
    assert engine._held_for_the_seams(out.state, out.verdict, for_family=False) == []


def test_r8_1_a_brand_over_carried_products_still_narrows_by_held_family():
    """Guard: the product axis carried (no switch, a plain brand refine over the held set) keeps held_family."""
    from app.services.chatbot import engine

    v = verdict(entities=[_brand()])
    out = _apply(_focus(), verdict_with(v, [_op("set", "brand")]))
    assert len(engine._held_for_the_seams(out.state, out.verdict, for_family=True)) == 3


def test_r8_1_names_own_subject_predicate():
    _seam_exists()
    assert chat_state.names_own_subject(verdict(entities=[_brand()])) is True
    assert chat_state.names_own_subject(verdict(entities=[_product(Y)])) is True
    assert chat_state.names_own_subject(verdict(entities=[])) is False
    held_row = {**_product(X), "current_message": False}
    assert chat_state.names_own_subject(verdict(entities=[held_row])) is False


# ---------------------------------------------------------------- AC-R8-2 (owner T9)
@pytest.mark.parametrize("op", SWITCH_OPS)
def test_r8_2_brand_and_tier_restated_everything_else_dropped(op):
    v = verdict(domain_hint="product_attachment", contains_flyer=True, access_levels=["office"],
                entities=[_brand("sorento", "SORENTO")])
    ops = _carry_ops(op, _op("set", "brand"), _op("set", "tier"))
    if op == "switch_domain":
        ops.insert(0, _op("keep"))
    out = _apply(_focus(), verdict_with(v, ops))
    shape = _shape(out)
    assert shape["products"] == [] and shape["warehouse"] == [] and shape["extra"] == {}, shape
    assert shape["tier"] == ["office"], f"tier is the restated value, got {shape['tier']}"
    assert _subject_codes(out) == []


# ---------------------------------------------------------------- AC-R8-3 (owner T10 / T15)
@pytest.mark.parametrize("op", SWITCH_OPS)
@pytest.mark.parametrize("with_set", [False, True], ids=["bare-switch", "set-product"])
def test_r8_3_a_typed_product_is_exactly_the_subject(op, with_set):
    v = verdict(domain_hint="product_attachment", entities=[_product(Y)])
    ops = _carry_ops(op, *([_op("set", "product")] if with_set else []))
    out = _apply(_focus(), verdict_with(v, ops))
    shape = _shape(out)
    assert shape["warehouse"] == [] and shape["extra"] == {} and shape["tier"] == [], shape
    assert shape["products"] == [], f"held products stay on the focus: {shape['products']}"
    assert _subject_codes(out) == [Y], _subject_codes(out)
    assert out.state.subject.provenance.get("product") == "said"


# ---------------------------------------------------------------- AC-R8-4 (same result for both ops)
SCENARIOS = {
    "T8": lambda: (verdict(domain_hint="product_attachment", contains_flyer=True, entities=[_brand()]),
                   [_op("set", "brand")]),
    "T9": lambda: (verdict(domain_hint="product_attachment", contains_flyer=True, access_levels=["office"],
                           entities=[_brand("sorento", "SORENTO")]),
                   [_op("set", "brand"), _op("set", "tier")]),
    "T10": lambda: (verdict(domain_hint="product_attachment", entities=[_product(Y)]), []),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_r8_4_switch_domain_and_new_subject_give_the_same_state(name):
    results = {}
    for op in SWITCH_OPS:
        v, ops = SCENARIOS[name]()
        out = _apply(_focus(), verdict_with(v, [_op(op), *ops]))
        results[op] = (_shape(out), _subject_codes(out))
    assert results["switch_domain"] == results["new_subject"], results


# ---------------------------------------------------------------- AC-R8-5 (bare switch keeps the subject)
@pytest.mark.parametrize("text_hint", ["eta", "price"])
def test_r8_5_a_bare_switch_keeps_the_held_subject_and_its_axes(text_hint):
    held = _focus([X], domains=("sales",))
    v = verdict(domain_hint="inventory" if text_hint == "eta" else "product_attachment", entities=[])
    out = _apply(held, verdict_with(v, [_op("switch_domain")]))
    shape = _shape(out)
    assert shape["products"] == [X], shape
    assert shape["warehouse"] == [{"raw": "frg", "hint": "warehouse", "current_message": False}]
    assert shape["tier"] == ["dealer"] and shape["extra"], shape
    assert _subject_codes(out) == [f"u-{X}"] or _subject_codes(out) == [X], _subject_codes(out)


# ---------------------------------------------------------------- AC-R8-6 (refine guards)
def test_r8_6_a_spec_over_held_products_with_a_switch_keeps_the_members():
    spec = entity("chrome", "specification", canonical_code="chrome", spec_key="colour", spec_value="chrome")
    v = verdict(domain_hint="inventory", entities=[spec])
    out = _apply(_focus(), verdict_with(v, [_op("set", "specification"), _op("switch_domain")]))
    assert _shape(out)["products"] == BASINS, "round 6 membership refine: the held products stay for the spec seam"


def test_r8_6_set_product_without_a_switch_keeps_the_other_held_axes():
    v = verdict(entities=[_product(Y)])
    out = _apply(_focus(domains=("inventory",)), verdict_with(v, [_op("set", "product")]))
    shape = _shape(out)
    assert shape["warehouse"] and shape["tier"] == ["dealer"] and shape["extra"], f"card R1 broken: {shape}"


# ---------------------------------------------------------------- AC-R8-7 (tier)
@pytest.mark.parametrize("op", SWITCH_OPS)
@pytest.mark.parametrize("ents", ["product", "brand"])
def test_r8_7_a_new_subject_without_a_tier_restatement_holds_no_tier(op, ents):
    e = [_product(Y)] if ents == "product" else [_brand()]
    out = _apply(_focus(), verdict_with(verdict(domain_hint="inventory", entities=e), [_op(op)]))
    assert _shape(out)["tier"] == [], _shape(out)["tier"]


def test_r8_7_new_subject_keeps_customers_and_brands_by_their_own_rules():
    out = _apply(_focus(), verdict_with(verdict(entities=[_product(Y)]), [_op("new_subject")]))
    shape = _shape(out)
    assert shape["customers"] == ["C0001"] and shape["brands"] == ["SORENTO"], shape


# ---------------------------------------------------------------- stale "frg" warehouse (crew addendum 1)
@pytest.mark.parametrize("op", SWITCH_OPS)
@pytest.mark.parametrize("ents", ["product", "brand"])
def test_r8_frg_warehouse_never_survives_a_new_subject(op, ents):
    from app.services.chatbot import turn_runtime

    e = [_product(Y)] if ents == "product" else [_brand()]
    focus = Focus(warehouse=[{"raw": "frg", "hint": "warehouse", "current_message": False}],
                  products=[_held(X)], domains=["inventory"])
    out = _apply(focus, verdict_with(verdict(domain_hint="product_attachment", entities=e), [_op(op)]))
    assert out.state.focus.warehouse == [], out.state.focus.warehouse
    carried = turn_runtime.outstanding_carry({}, out.state.focus, {})
    assert "outstanding_carried_location_token" not in carried, carried


# ---------------------------------------------------------------- chains (crew addendum 2, 3)
def test_r8_chain_new_subject_then_bare_follow_up_holds_only_the_new_subject():
    a = _apply(_focus([X]), verdict_with(verdict(domain_hint="product_attachment", entities=[_product(Y)]),
                                         [_op("switch_domain"), _op("set", "product")]))
    # Turn A's kind rules settle the said product onto the focus before turn B reads it.
    focus_b = copy.deepcopy(a.state.focus)
    focus_b.products = [_held(Y)]
    focus_b.domains = ["product_attachment"]
    state_b = State(focus=focus_b, turn_no=4)
    b = chat_state.apply_changes(state_b, verdict_with(verdict(domain_hint="inventory", entities=[]), [_op("switch_domain")]),
                                 open_question=None, domains=DOMAINS, kinds=KINDS, brands=BRANDS,
                                 positions_read_elsewhere=False)
    assert b.valid is True
    shape = _shape(b)
    assert shape["products"] == [Y], shape
    assert shape["warehouse"] == [] and shape["tier"] == [] and shape["extra"] == {}, shape
    assert X not in str(_subject_codes(b))


def test_r8_chain_t8_then_t9_the_second_turn_starts_from_the_first_output():
    t8 = _apply(_focus(), verdict_with(
        verdict(domain_hint="product_attachment", contains_flyer=True, entities=[_brand()]),
        [_op("switch_domain"), _op("set", "brand")]))
    s8 = _shape(t8)
    assert s8["products"] == [] and s8["warehouse"] == [], s8
    # T9: the brand sticks (set by T8's kind rules); the second flyer ask restates brand + tier.
    focus9 = copy.deepcopy(t8.state.focus)
    focus9.brands = ["SRT"]
    t9 = chat_state.apply_changes(
        State(focus=focus9, turn_no=5),
        verdict_with(verdict(domain_hint="product_attachment", contains_flyer=True, access_levels=["office"],
                             entities=[_brand("sorento", "SORENTO")]),
                     [_op("keep"), _op("set", "brand"), _op("set", "tier"), _op("switch_domain")]),
        open_question=None, domains=DOMAINS, kinds=KINDS, brands=BRANDS, positions_read_elsewhere=False)
    assert t9.valid is True
    s9 = _shape(t9)
    assert s9["products"] == [] and s9["warehouse"] == [] and s9["extra"] == {}, s9
    assert s9["tier"] == ["office"], s9


# ---------------------------------------------------------------- engine level (EngineConsole, live shape)
HELD3 = ["SRTWC286-SH", "SRTWC286-SH-150", "SRTWC286-SH-200"]  # stand-ins for the 3 RG basins


def _seed_brands(session_factory, c):
    """Real brand rows (SRT holds the stand-in basins, SORENTO exists) so `set brand` validates."""
    import uuid

    from app.models.product import Brand, Product
    from tests.chatbot._r9_engine_console import SORENTO

    db = session_factory()
    db.info["company_scope"] = frozenset({SORENTO})
    ids = {}
    for code, name in (("SRT", "SRT"), ("SORENTO", "Sorento")):
        row = Brand(id=str(uuid.uuid4()), brand_code=code, brand_name=name, company_id=SORENTO)
        db.add(row)
        db.flush()
        ids[code] = row.id
    for k in HELD3:
        db.query(Product).filter(Product.id == c.uuid_of[k]).update({"brand_id": ids["SRT"]})
    db.commit()


def _held_console(session_factory, monkeypatch, stub_access, phone, *, tier=False, extra=False):
    from app.services.chatbot.lanes.business import services as business_services
    from tests.chatbot.test_chat_state_r7_last_referent import _with_state_block
    from tests.chatbot.test_quoted_reply_engine import _console, _focus_wire, _store_turn

    c = _console(session_factory, monkeypatch, stub_access, phone)
    _seed_brands(session_factory, c)
    monkeypatch.setattr(business_services, "_access_types",
                        lambda db, default_space_id=None: (lambda **_: [{"name": "Sorento Dealer"}]))
    _with_state_block(monkeypatch)
    focus = _focus_wire(c, HELD3[0])
    focus["products"] = [{"raw": k, "canonical_code": k, "uuid": c.uuid_of[k], "hint": "product"} for k in HELD3]
    focus["warehouse"] = [{"raw": "frg", "hint": "warehouse"}]
    if tier:
        focus["tier"] = ["sorento_dealer"]
    if extra:
        focus["extra"] = {"order": [{"raw": "SO0001", "hint": "order"}]}
    _store_turn(c, reply_text="held", focus=focus, turn_no=1, age_s=900)
    c.state = {"focus": focus, "open_question": None}
    return c


def _promo_args(c):
    return [a for n, a in c.tool_calls if n == "crm_marketing_promotions_list"]


def _wire_ids(args):
    return [pid for a in args for pid in (a.get("product_ids") or [])]


def test_r8_engine_t8_a_brand_flyer_switch_does_not_ride_the_held_basins_or_frg(session_factory, monkeypatch, stub_access):
    from tests.chatbot._r9_engine_console import reply

    c = _held_console(session_factory, monkeypatch, stub_access, "+60900000881")
    out = c.say("send me srt a3 flyer", reply(
        domain_hint="promotion", intent_hint=None, contains_flyer=True, access_levels=["sorento_dealer"],
        entities=[_brand()], state_changes=[_op("switch_domain"), _op("set", "brand")]))
    assert "(promotion)" not in out, f"a kind pick on a held code: {out[:300]}"
    assert "Location: frg" not in out, f"the stale warehouse filtered the reply: {out[:300]}"
    assert not _wire_ids(_promo_args(c)), ("held product ids reached the promotions fetch", _promo_args(c))


def test_r8_engine_t9_after_t8_the_promotions_fetch_carries_no_held_product_ids(session_factory, monkeypatch, stub_access):
    from tests.chatbot._r9_engine_console import reply

    c = _held_console(session_factory, monkeypatch, stub_access, "+60900000882", tier=True, extra=True)
    c.say("send me srt a3 flyer", reply(
        domain_hint="promotion", intent_hint=None, contains_flyer=True, access_levels=["sorento_dealer"],
        entities=[_brand()], state_changes=[_op("switch_domain"), _op("set", "brand")]))
    c.tool_calls.clear()
    c.say("send me sorento a3 flyer", reply(
        domain_hint="promotion", intent_hint=None, contains_flyer=True, access_levels=["sorento_dealer"],
        entities=[_brand("sorento", "SORENTO")],
        state_changes=[_op("keep"), _op("set", "brand"), _op("set", "tier"), _op("switch_domain")]))
    args = _promo_args(c)
    assert args, ("the promotions tool was never called", [n for n, _ in c.tool_calls])
    assert not _wire_ids(args), ("held product_ids rode the promotions fetch", args)


# ---------------------------------------------------------------- AC-R8-8 (state off, behavioural)
def test_r8_8_state_off_a_new_ask_still_drops_tier_and_extra(session_factory, monkeypatch, stub_access):
    """State block OFF (console default), no state_changes: apply.py's new_ask_drops_* fire as today."""
    from tests.chatbot._r9_engine_console import product, stock
    from tests.chatbot.test_quoted_reply_engine import _console, _focus_wire, _store_turn

    c = _console(session_factory, monkeypatch, stub_access, "+60900000883")
    focus = _focus_wire(c, HELD3[0])
    focus["tier"] = ["sorento_dealer"]
    focus["extra"] = {"attachment_type": [{"raw": "brochure", "hint": "attachment_type"}]}
    _store_turn(c, reply_text="held", focus=focus, turn_no=1, age_s=900)
    c.state = {"focus": focus, "open_question": None}
    c.say("check stock SRTWC287-S-150", stock(product("SRTWC287-S-150"), entity_op="replace"))
    fired = [r for t in c.traces for r in t.rules_fired]
    assert "new_ask_drops_tier" in fired and "new_ask_drops_attachment_type" in fired, fired


def test_r8_8_state_off_held_family_brand_only_branch_still_receives_the_held_products(
    session_factory, monkeypatch, stub_access
):
    import dataclasses

    from app.services.chatbot import engine
    from app.services.chatbot.head import held_family, parser as parser_mod
    from tests.chatbot._r9_engine_console import reply
    from tests.chatbot.test_quoted_reply_engine import _console, _focus_wire, _store_turn

    c = _console(session_factory, monkeypatch, stub_access, "+60900000884")
    real_cfg = parser_mod.resolve_config
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, *, current_date, override_version_id=None: dataclasses.replace(
        real_cfg(db, current_date=current_date, override_version_id=override_version_id), closed_lists=True))
    focus = _focus_wire(c, HELD3[0])
    focus["products"] = [{"raw": k, "canonical_code": k, "uuid": c.uuid_of[k], "hint": "product"} for k in HELD3]
    _store_turn(c, reply_text="held", focus=focus, turn_no=1, age_s=900)
    c.state = {"focus": focus, "open_question": None}
    seen = []
    real = held_family.narrow_held_family

    def spy(db, v, held):
        seen.append([p.get("canonical_code") for p in held])
        return real(db, v, held)

    monkeypatch.setattr(held_family, "narrow_held_family", spy)
    c.say("srt ones", reply(entities=[_brand()]))
    assert seen and seen[0] == HELD3, ("state off: held_family must still get the held products", seen)
