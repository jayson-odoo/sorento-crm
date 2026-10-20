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
    # Whether or not a promotion tool runs: once the held ids are gone the brand (SORENTO owns no
    # products here) is a described set that qualifies nothing, so no tool may run at all (evidence
    # class (c), Fix 3, another lane). Red at 0f8e2661df: crm_marketing_promotion_products_list was
    # called with the 3 held product_ids.
    held = {c.uuid_of[k] for k in HELD3}
    sent = [(n, a) for n, a in c.tool_calls if "promotion" in n and held & set(a.get("product_ids") or [])]
    assert not sent, ("held product_ids rode a promotion fetch", sent)


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


def test_r8_1_a_brand_over_carried_products_still_narrows_by_held_family(session_factory, monkeypatch, stub_access):
    """Guard (behavioural): the product axis carried (a refine, NO switch) and a message naming only a
    brand: held_family runs and narrows the held set, under the state gate."""
    import dataclasses

    from app.services.chatbot.head import held_family, parser as parser_mod
    from tests.chatbot._r9_engine_console import reply

    c = _held_console(session_factory, monkeypatch, stub_access, "+60900000885")
    gated = parser_mod.resolve_config
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, *, current_date, override_version_id=None: dataclasses.replace(
        gated(db, current_date=current_date, override_version_id=override_version_id), closed_lists=True))
    seen = []
    real = held_family.narrow_held_family

    def spy(db, v, held):
        out = real(db, v, held)
        seen.append(([p.get("canonical_code") for p in held], out[1]))
        return out

    monkeypatch.setattr(held_family, "narrow_held_family", spy)
    c.say("srt ones", reply(entities=[_brand()], state_changes=[_op("set", "brand")]))
    assert seen, "held_family never ran on a carried product axis"
    assert seen[0][0] == HELD3, seen
    assert seen[0][1] and sorted(seen[0][1].get("matched") or []) == sorted(HELD3), seen


# ---------------------------------------------------------------- review round: B1 implicit switch rebuilds
IMPLICIT_OPS = {"keep": [_op("keep")], "close_question": [_op("close_question")]}


@pytest.mark.parametrize("ops", sorted(IMPLICIT_OPS))
def test_r8_b1_an_implicit_switch_naming_a_new_product_rebuilds(ops):
    """Real $0-delta shapes: "Check eta , <code>" [close_question]; "<code> eta" [keep]. No switch op,
    but the domain changes (held inventory, message incoming) and a NEW product is typed."""
    out = _apply(_focus(domains=("inventory",)), verdict_with(
        verdict(domain_hint="incoming", entities=[_product(Y)]), list(IMPLICIT_OPS[ops])))
    shape = _shape(out)
    assert shape["warehouse"] == [] and shape["extra"] == {} and shape["tier"] == [], shape
    assert shape["products"] == [], f"held products rode an implicit switch: {shape['products']}"
    assert _subject_codes(out) == [Y], _subject_codes(out)


@pytest.mark.parametrize("ops", sorted(IMPLICIT_OPS))
def test_r8_b1_engine_an_implicit_switch_fetches_the_new_product_only(session_factory, monkeypatch, stub_access, ops):
    from tests.chatbot._r9_engine_console import reply

    c = _held_console(session_factory, monkeypatch, stub_access, "+60900000886" if ops == "keep" else "+60900000887",
                      tier=True, extra=True)
    new = "SRTWC287-S-150"
    c.tool_calls.clear()
    c.say(f"check eta, {new}", reply(domain_hint="incoming", intent_hint=None, entities=[_product(new)],
                                      state_changes=list(IMPLICIT_OPS[ops])))
    held = {c.uuid_of[k] for k in HELD3}
    sent = [(n, a) for n, a in c.tool_calls if held & set(str(a.get("product_ids") or []).replace("'", " ").replace("[", " ").replace("]", " ").replace(",", " ").split())]
    assert not sent, ("held product ids rode the implicit switch fetch", sent)
    assert any(c.uuid_of[new] in str(a) for _n, a in c.tool_calls), ("the new product was never fetched", [n for n, _ in c.tool_calls])


def test_r8_nit_domains_equal_across_explicit_and_implicit_switch():
    shapes = {}
    for name, ops in (("explicit", [_op("switch_domain")]), ("implicit", [_op("keep")])):
        out = _apply(_focus(domains=("inventory",)), verdict_with(
            verdict(domain_hint="incoming", entities=[_product(Y)]), ops))
        shapes[name] = (_shape(out), list(out.state.focus.domains))
    assert shapes["explicit"] == shapes["implicit"], shapes
    assert shapes["implicit"][1] == ["incoming"]


# ---------------------------------------------------------------- review round: B2 an answer never rebuilds
CODES2 = ["SRTWC286-SH", "SRTWC286-SH-P"]


def _roster_state():
    from app.services.chatbot.turn.pending import ask
    from app.services.chatbot.turn.tail import last_list_after

    pending = ask("product_pick", [
        {"position": i, "label": c, "code": c, "name": None, "entity_type": "product", "payload": {}}
        for i, c in enumerate(CODES2, 1)], asked_at_turn=2, payload={"domain": "incoming"})
    ll = last_list_after(None, question=pending, sections=[], turn_no=2)
    return pending, State(focus=Focus(domains=["incoming"], last_list=ll, tier=["dealer"]), pending=pending,
                          turn_no=3, state_path=True)


def _roster_turn(ops, hint="inventory", extra_v=None):
    from app.services.chatbot.turn import question as question_mod
    from app.services.chatbot.turn.apply import apply
    from tests.chatbot._turn_helpers import build_policy

    pending, st = _roster_state()
    v = verdict(domain_hint=hint, reference_positions=[1] if any(o.get("op") == "pick" for o in ops) else [],
                entities=[entity(CODES2[0], "product", canonical_code=CODES2[0])], state_changes=ops, **(extra_v or {}))
    a = chat_state.apply_changes(st, v, open_question=question_mod.of_pending(pending), domains=DOMAINS,
                                 kinds=KINDS, brands=["SORENTO"], positions_read_elsewhere=False)
    assert a.valid is True, a.log.get("rejected")
    _s, plan = apply(a.state, a.verdict, build_policy())
    return a, plan


@pytest.mark.parametrize("ops", [
    [{"op": "pick", "axis": None, "position": 1}],
    [{"op": "pick", "axis": None, "position": 1}, _op("switch_domain")],
], ids=["pick-implicit-domain", "pick-explicit-switch"])
def test_r8_b2_a_pick_over_an_open_roster_never_rebuilds(ops):
    a, plan = _roster_turn(ops)
    fired = plan.trace.rules_fired
    assert "open_question_answer_pick" in fired and "pick_in_roster_domain" in fired, fired
    assert list(plan.domains) == ["incoming"], plan.domains
    assert a.state.focus.tier == ["dealer"], f"the tier was rebuilt away: {a.state.focus.tier}"
    assert a.state.pending is not None, "the open roster was wiped before it was answered"


def test_r8_b2_an_answer_op_with_a_typed_product_and_a_domain_change_never_rebuilds():
    a, plan = _roster_turn([_op("answer")], extra_v={"open_question_answer": {
        "mode": "pick", "picked": [1], "items": [], "qty_for_all": None}})
    assert a.state.focus.tier == ["dealer"], a.state.focus.tier
    assert a.state.pending is not None, "the open roster was wiped before it was answered"


def test_r8_b2_guard_explicit_new_subject_still_rebuilds():
    a, _plan = _roster_turn([_op("new_subject")])
    assert a.state.focus.tier == [] and a.state.pending is None


# ---------------------------------------------------------------- C5: a file-kind change drops the held scheme
# Smoke EXPLORE-1020: "<scheme> cert for <code>" then "drawing also". The scheme is held on
# focus.extra["certificate"] (row hint certificate, listed cert_scheme, certificate_uuids), the file
# kind on focus.extra["attachment_type"]. The scheme qualified the OLD file kind, so a follow-up that
# changes the kind keeps the product and drops the scheme. Reproduced on fb96100fb0: the drawing fetch
# carried the certificate_ids and the reply said "But no ZZT Drawing matched these".
from tests.chatbot.test_chat_state_r6_s3_ops_decide import _turns as _c5_turns, applied  # noqa: E402,F401
from tests.chatbot.test_closed_lists_scheme_index import (  # noqa: E402,F401 - fixtures used by name
    CODE as C5_CODE, PRODUCT as C5_PRODUCT, _file_ask, _file_fetches, _scheme, _seed, seeded, session_factory,
)

SCHEME_ROW = {"raw": "span", "hint": "certificate", "listed": "cert_scheme", "listed_item": "SPAN", "canonical_code": "SPAN",
              "current_message": False, "certificate_uuids": ["c-span"]}
CERT_KIND_ROW = {"raw": "ZZT Certification", "hint": "attachment_type", "listed": "cert_kind", "listed_item": "ZZT Certification",
                 "canonical_code": "ZZT Certification", "current_message": False}
DRAWING = {"raw": "drawing", "hint": "attachment_type", "canonical_code": "ZZT Drawing", "listed_item": "ZZT Drawing",
           "current_message": True, "confident": True}
KIND_OPS = {
    "set": [_op("set", "attachment_type")],
    "keep+set": [_op("keep"), _op("set", "attachment_type")],
    "switch+set": [_op("switch_domain"), _op("set", "attachment_type")],
}


def _c5_focus():
    return Focus(products=[_held("SRTFC2043")], domains=["product_attachment"],
                 extra={"certificate": [dict(SCHEME_ROW)], "attachment_type": [dict(CERT_KIND_ROW)]})


@pytest.mark.parametrize("name", sorted(KIND_OPS))
def test_r8_c5_apply_a_file_kind_change_keeps_the_product_and_drops_the_scheme(name):
    v = verdict(domain_hint="product_attachment", entities=[dict(DRAWING)])
    out = _apply(_c5_focus(), verdict_with(v, list(KIND_OPS[name])))
    f = out.state.focus
    assert [p["canonical_code"] for p in f.products] == ["SRTFC2043"], "the held product must stay"
    assert not (f.extra or {}).get("certificate"), f"the held scheme rode a file-kind change: {f.extra}"
    assert out.state.subject.provenance.get("product") == "held"


def test_r8_c5_apply_the_same_result_with_and_without_switch_domain():
    shapes = []
    for name in ("set", "switch+set"):
        v = verdict(domain_hint="product_attachment", entities=[dict(DRAWING)])
        out = _apply(_c5_focus(), verdict_with(v, list(KIND_OPS[name])))
        f = out.state.focus
        shapes.append(([p["canonical_code"] for p in f.products], bool((f.extra or {}).get("certificate"))))
    assert shapes[0] == shapes[1], shapes


def test_r8_c5_apply_guard_a_follow_up_that_keeps_the_file_kind_keeps_the_scheme():
    """"and srtfc2044?": a new product, no file kind named."""
    v = verdict(domain_hint="product_attachment", entities=[_product("SRTFC2044")])
    out = _apply(_c5_focus(), verdict_with(v, [_op("set", "product")]))
    assert (out.state.focus.extra or {}).get("certificate"), "the scheme must stay when the file kind does not change"


def test_r8_c5_apply_guard_restating_the_same_file_kind_keeps_the_scheme():
    same = {**CERT_KIND_ROW, "current_message": True}
    v = verdict(domain_hint="product_attachment", entities=[same])
    out = _apply(_c5_focus(), verdict_with(v, [_op("set", "attachment_type")]))
    assert (out.state.focus.extra or {}).get("certificate"), "the same file kind restated is not a kind change"


def _c5_seed_drawing(session_factory, product_id):
    from app.models.product import ProductAttachment
    from app.models.resources import Attachment, AttachmentType
    from app.services.company_scope import DEFAULT_COMPANY_ID

    db = session_factory()
    t = AttachmentType(id=str(uuid.uuid4()), type_name="ZZT Drawing", description="d", allowed_extensions="pdf", is_certificate=False)
    db.add(t)
    db.flush()
    a = Attachment(id=str(uuid.uuid4()), original_filename=f"{C5_CODE}_DWG.pdf", stored_filename=uuid.uuid4().hex,
                   file_path="https://cdn.test/d.pdf", attachment_type_id=t.id, is_deleted=False, company_id=DEFAULT_COMPANY_ID)
    db.add(a)
    db.flush()
    db.add(ProductAttachment(id=str(uuid.uuid4()), product_id=product_id, attachment_id=a.id, company_id=DEFAULT_COMPANY_ID))
    db.commit()


import uuid  # noqa: E402


def _c5_two_turns(session_factory, stub_access, monkeypatch, ops, turn2_entities=None):
    ids = _seed(session_factory)
    _c5_seed_drawing(session_factory, ids["product"])
    a1 = _file_ask(C5_PRODUCT, _scheme("zzspan", "ZZSPAN"))
    a1["state_changes"] = [_op("set", "product"), _op("set", "attachment_type")]
    a2 = _file_ask(*(turn2_entities if turn2_entities is not None else [dict(DRAWING)]))
    a2["state_changes"] = ops
    (_r1, _c1), (r2, c2) = _c5_turns(session_factory, stub_access, monkeypatch, [(f"zzspan cert for {C5_CODE}", a1), ("drawing also", a2)])
    return ids, (r2.reply or {}).get("text") or "", _file_fetches(c2)


@pytest.mark.parametrize("name", sorted(KIND_OPS))
def test_r8_c5_engine_drawing_also_fetches_the_drawing_without_the_scheme(session_factory, seeded, stub_access, monkeypatch, applied, name):
    ids, text, fetches = _c5_two_turns(session_factory, stub_access, monkeypatch, list(KIND_OPS[name]))
    assert len(applied) >= 2, "the state path did not run"
    assert fetches, "no attachment fetch on the drawing turn"
    assert fetches[0].get("product_ids") == [ids["product"]], fetches
    assert not fetches[0].get("certificate_ids"), ("the scheme rode the drawing fetch", fetches[0])
    assert fetches[0].get("attachment_type_ids"), fetches
    assert "no ZZT Drawing matched" not in text and "Couldn't find" not in text, text


def test_r8_c5_engine_guard_a_follow_up_that_keeps_the_file_kind_keeps_the_scheme(session_factory, seeded, stub_access, monkeypatch, applied):
    ids, _text, fetches = _c5_two_turns(session_factory, stub_access, monkeypatch, [_op("keep")], turn2_entities=[dict(C5_PRODUCT)])
    assert fetches and ids["ZZSPAN"] in (fetches[0].get("certificate_ids") or []), fetches


def test_r8_c5_state_off_the_drawing_fetch_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    """State off (no state block, no state_changes): today's behaviour, pinned: the scheme still rides."""
    import json

    from app.services.ai_assistant_service import MCPRuntimeClient
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.head import parser as parser_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests.chatbot.test_closed_lists_scheme_index import _message
    from tests.chatbot.test_engine import _envelope

    ids = _seed(session_factory)
    _c5_seed_drawing(session_factory, ids["product"])
    queue = [_file_ask(C5_PRODUCT, _scheme("zzspan", "ZZSPAN")), _file_ask(dict(DRAWING))]
    monkeypatch.setattr(parser_mod, "resolve_config", lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
        system_prompt="stub", prompt_version=1, provider="openai", model="m", api_key="k", closed_lists=True))
    monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: queue.pop(0))
    monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({DEFAULT_COMPANY_ID}))
    calls = []
    monkeypatch.setattr(MCPRuntimeClient, "call_tool", lambda self, name, args: calls.append((name, args)) or json.dumps({"ok": True, "items": []}))
    stub_access()
    engine_mod.run_turn(_envelope(message=_message("zzspan cert", 0)), session_factory=session_factory)
    calls.clear()
    engine_mod.run_turn(_envelope(message=_message("drawing also", 1)), session_factory=session_factory)
    fetches = _file_fetches(calls)
    assert fetches and fetches[0].get("certificate_ids"), ("state-off behaviour changed", fetches)
