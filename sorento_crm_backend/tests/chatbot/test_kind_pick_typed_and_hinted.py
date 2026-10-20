"""Kind pick: a hinted kind that is the ONLY exact whole-token kind wins, and a pick is asked only
for a token typed THIS message (owner run 1020 class b). `typed` is the FOLDED own text of the
message (`token_key` of the text without the reply-to block, plus the codes read from the turn's
media); a token is typed when `token_key(raw)` is a substring of it. Pure tests over hand-built
`resolved` / `exact` maps, then the engine seam through a real turn."""
from __future__ import annotations

from typing import Any

from app.services.chatbot.turn.reconcile import apply_reconciliation
from app.services.chatbot.turn.state import token_key


def _ent(raw: str, hint: str) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}


def _fold(text: str) -> str:
    return token_key(text)


# ---------------------------------------------------------------- rule A: hinted kind alone is exact


def test_t15_hinted_kind_only_exact_keeps_its_kind():
    r = apply_reconciliation(
        [_ent("SRTKS8551", "product")],
        {"SRTKS8551": {"product": 1, "promotion": 1}},
        exact={"SRTKS8551": {"product": 1}},
        typed=_fold("SRTKS8551"),
    )
    assert r.kind_pick_options is None
    assert [e["hint"] for e in r.entities] == ["product"]


def test_t15_hinted_exact_kind_wins_without_typed():
    r = apply_reconciliation(
        [_ent("SRTKS8551", "product")],
        {"SRTKS8551": {"product": 1, "promotion": 1}},
        exact={"SRTKS8551": {"product": 1}},
    )
    assert r.kind_pick_options is None
    assert [e["hint"] for e in r.entities] == ["product"]


def test_po_word_two_exact_kinds_still_asks_ac13():
    r = apply_reconciliation(
        [_ent("4500123", "purchase_order")],
        {"4500123": {"purchase_order": 1, "customer_po_ref": 1}},
        exact={"4500123": {"purchase_order": 1, "customer_po_ref": 1}},
    )
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["purchase_order", "customer_po_ref"]


def test_sorento_hinted_customer_with_two_exact_kinds_still_asks():
    both = {"Sorento": {"customer": 1, "transporter": 1}}
    r = apply_reconciliation([_ent("Sorento", "customer")], both, exact=both)
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["customer", "transporter"]


def test_control_hint_without_exact_hit_still_asks():
    both = {"Sorento": {"transporter": 1, "customer": 1}}
    r = apply_reconciliation([_ent("Sorento", "brand")], both, exact=both, typed=_fold("Sorento"))
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["customer", "transporter"]


def test_reference_narrow_regression_named_kind_beats_other_kind():
    r = apply_reconciliation(
        [_ent("202610-0838", "sales_order")],
        {"202610-0838": {"sales_order": 1, "customer_order": 1}},
        exact={"202610-0838": {"sales_order": 1}},
    )
    assert r.kind_pick_options is None
    assert [e["hint"] for e in r.entities] == ["sales_order"]
    assert r.reconciled == []


# ---------------------------------------------------------------- rule B: typed by containment

_PROMO_HITS = {"SRTKS8551": {"product": 1, "promotion": 1}}
_PROMO_EXACT = {"SRTKS8551": {"promotion": 1}}


def _asks(text: str, raw: str = "SRTKS8551") -> bool:
    hits = {raw: _PROMO_HITS["SRTKS8551"]}
    exact = {raw: _PROMO_EXACT["SRTKS8551"]}
    r = apply_reconciliation([_ent(raw, "product")], hits, exact=exact, typed=_fold(text))
    return r.kind_pick_options is not None


def test_typed_inside_a_question():
    assert _asks("promo for SRTKS8551?")


def test_typed_with_a_trailing_comma():
    assert _asks("SRTKS8551, any promo")


def test_typed_in_brackets():
    assert _asks("(SRTKS8551)")


def test_typed_with_a_glued_quantity():
    assert _asks("SRTKS8551x10")


def test_typed_beside_cjk():
    assert _asks("SRTKS8551有promo吗")


def test_typed_with_a_space_inside_the_code():
    assert _asks("SRT KS8551 promo")


def test_typed_on_the_second_own_line():
    assert _asks("Hi boss\nSRTKS8551 promo?")


def test_untyped_held_token_arms_nothing():
    e = _ent("SRTWB1096-RG", "product")
    r = apply_reconciliation(
        [e],
        {"SRTWB1096-RG": {"product": 1, "promotion": 1}},
        exact={"SRTWB1096-RG": {"promotion": 1}},
        typed=_fold("A2 flyer"),
    )
    assert r.kind_pick_options is None
    assert r.entities == [e]


def test_typed_none_keeps_todays_pick():
    r = apply_reconciliation(
        [_ent("SRTWB1096-RG", "product")],
        {"SRTWB1096-RG": {"product": 1, "promotion": 1}},
        exact={"SRTWB1096-RG": {"promotion": 1}},
    )
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["product", "promotion"]


def test_multi_word_raw_is_typed_when_its_folded_form_is_inside_the_text():
    resolved = {"water closet": {"customer": 1, "transporter": 1}}
    asked = apply_reconciliation(
        [_ent("water closet", "brand")], resolved, exact=resolved, typed=_fold("any stock of water closet?")
    )
    assert asked.kind_pick_options is not None
    unasked = apply_reconciliation(
        [_ent("water closet", "brand")], resolved, exact=resolved, typed=_fold("water bottle")
    )
    assert unasked.kind_pick_options is None
    assert [e["hint"] for e in unasked.entities] == ["brand"]


def test_only_the_typed_ambiguous_token_is_asked():
    resolved = {
        "Alpha": {"customer": 1, "transporter": 1},
        "Beta": {"customer": 1, "transporter": 1},
    }
    r = apply_reconciliation(
        [_ent("Alpha", "brand"), _ent("Beta", "brand")], resolved, exact=resolved, typed=_fold("stock of Beta")
    )
    assert r.kind_pick_options is not None
    assert {o["raw"] for o in r.kind_pick_options} == {"Beta"}
    assert r.queued_kind_picks == []
    assert len(r.entities) == 2


# ---------------------------------------------------------------- engine seam: what turn_apply is given


def _qf_with(*raws: str, hint: str = "product") -> dict[str, Any]:
    from tests.chatbot.test_engine import _parser_output

    return _parser_output(
        entities=[
            {"raw": r, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}
            for r in raws
        ]
    )


def _spy_turn_apply(monkeypatch) -> list[dict[str, Any]]:
    from app.services.chatbot import engine as engine_mod

    seen: list[dict[str, Any]] = []
    real = engine_mod.turn_apply

    def spy(state_in, *args, **kwargs):
        seen.append(dict(kwargs))
        return real(state_in, *args, **kwargs)

    monkeypatch.setattr(engine_mod, "turn_apply", spy)
    return seen


def _quote_envelope(monkeypatch, quoted: str) -> None:
    from tests.chatbot import test_outstanding_lane as lane

    real = lane._envelope

    def wrapped(*a, **kw):
        env = real(*a, **kw)
        env.message["message"]["replyTo"] = {"message": {"text": quoted}}
        return env

    monkeypatch.setattr(lane, "_envelope", wrapped)


def _run(session_factory, monkeypatch, *, text: str, raw: str, msg_id: str, also: str | None = None):
    """`also` is a second entity, current_message true, resolvable, that the text does not name."""
    from tests.chatbot.test_outstanding_lane import _run_turn, _seed_contact

    _seed_contact(session_factory, variables={})
    from tests.chatbot.test_outstanding_lane import PRODUCT_UUID

    raws = [raw] + ([also] if also else [])
    matches = {
        r: {"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": r, "match_tier": "exact"}
        for r in raws
    }
    return _run_turn(
        session_factory, monkeypatch, qf=_qf_with(*raws), text_body=text, msg_id=msg_id, matches=matches
    )


def test_engine_hands_apply_the_folded_own_text(session_factory, monkeypatch):
    seen = _spy_turn_apply(monkeypatch)
    _run(session_factory, monkeypatch, text="Promo for SRTKS8551 ?", raw="SRTKS8551", msg_id="zzt-kp-own-text")
    typed = [k.get("typed") for k in seen if "typed" in k]
    assert typed, "engine passed no typed to turn_apply"
    assert all(isinstance(t, str) and "srtks8551" in t for t in typed), typed


def test_engine_typed_text_leaves_out_the_reply_to_block(session_factory, monkeypatch):
    seen = _spy_turn_apply(monkeypatch)
    _quote_envelope(monkeypatch, "earlier we spoke of SRTWB1096-RG")
    _run(
        session_factory, monkeypatch, text="any promo SRTKS8551", raw="SRTKS8551", msg_id="zzt-kp-quote",
        also="SRTWB1096-RG",
    )
    typed = [k.get("typed") for k in seen if "typed" in k]
    assert typed, "engine passed no typed to turn_apply"
    assert all(isinstance(t, str) and "anypromosrtks8551" in t and "srtwb1096rg" not in t for t in typed), typed


def test_engine_untyped_held_entity_arms_no_kind_pick(session_factory, monkeypatch):
    """T8: the entity is current_message true but its raw is not in the message text."""
    seen = _spy_turn_apply(monkeypatch)
    _run(
        session_factory, monkeypatch, text="A2 flyer SRTKS8551", raw="SRTKS8551", msg_id="zzt-kp-t8",
        also="SRTWB1096-RG",
    )
    raw = "SRTWB1096-RG"
    kinds = {raw: {"product": 1, "promotion": 1}}
    typed_values = [k.get("typed") for k in seen if "typed" in k]
    assert typed_values, "engine passed no typed to turn_apply"
    for typed in typed_values:
        r = apply_reconciliation(
            [_ent(raw, "product")], kinds, exact={raw: {"promotion": 1}}, typed=typed
        )
        assert isinstance(typed, str) and "srtwb1096rg" not in typed, typed
        assert r.kind_pick_options is None, typed
