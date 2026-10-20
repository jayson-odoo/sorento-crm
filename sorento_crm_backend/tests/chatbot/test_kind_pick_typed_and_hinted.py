"""Kind pick: a hinted kind with an exact whole-token hit wins, and a pick is asked only for a
token typed THIS message (owner run 1020 class b). Pure: `apply_reconciliation` over
hand-built maps; `typed` is the set of folded keys of the message's own first-line words."""
from __future__ import annotations

from typing import Any

from app.services.chatbot.turn.reconcile import apply_reconciliation
from app.services.chatbot.turn.state import token_key


def _ent(raw: str, hint: str) -> dict[str, Any]:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True}


def _typed(*words: str) -> frozenset[str]:
    return frozenset(token_key(w) for w in words)


def test_t15_hinted_kind_with_exact_hit_keeps_its_kind():
    r = apply_reconciliation(
        [_ent("SRTKS8551", "product")],
        {"SRTKS8551": {"product": 1, "promotion": 1}},
        exact={"SRTKS8551": {"product": 1}},
        typed=_typed("SRTKS8551"),
    )
    assert r.kind_pick_options is None
    assert [e["hint"] for e in r.entities] == ["product"]


def test_t8_untyped_token_never_arms_a_pick():
    e = _ent("SRTWB1096-RG", "product")
    r = apply_reconciliation(
        [e],
        {"SRTWB1096-RG": {"product": 1, "promotion": 1}},
        exact={"SRTWB1096-RG": {"promotion": 1}},
        typed=_typed("hello", "stock"),
    )
    assert r.kind_pick_options is None
    assert r.entities == [e]


def test_control_typed_token_without_hinted_exact_hit_still_asks():
    r = apply_reconciliation(
        [_ent("Sorento", "brand")],
        {"Sorento": {"transporter": 1, "customer": 1}},
        exact={"Sorento": {"transporter": 1, "customer": 1}},
    )
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["customer", "transporter"]


def test_control_typed_omitted_keeps_todays_pick():
    r = apply_reconciliation(
        [_ent("SRTWB1096-RG", "product")],
        {"SRTWB1096-RG": {"product": 1, "promotion": 1}},
        exact={"SRTWB1096-RG": {"promotion": 1}},
    )
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["product", "promotion"]


def test_multi_word_raw_is_typed_only_when_every_word_is():
    resolved = {"water closet": {"customer": 1, "transporter": 1}}
    both = apply_reconciliation(
        [_ent("water closet", "brand")], resolved, typed=_typed("water", "closet")
    )
    assert both.kind_pick_options is not None
    one = apply_reconciliation([_ent("water closet", "brand")], resolved, typed=_typed("water"))
    assert one.kind_pick_options is None
    assert [e["hint"] for e in one.entities] == ["brand"]


def test_only_the_typed_ambiguous_token_is_asked():
    resolved = {
        "Alpha": {"customer": 1, "transporter": 1},
        "Beta": {"customer": 1, "transporter": 1},
    }
    r = apply_reconciliation(
        [_ent("Alpha", "brand"), _ent("Beta", "brand")], resolved, typed=_typed("Beta")
    )
    assert r.kind_pick_options is not None
    assert {o["raw"] for o in r.kind_pick_options} == {"Beta"}
    assert r.queued_kind_picks == []
    assert len(r.entities) == 2


def test_reference_narrow_regression_named_kind_beats_other_kind():
    r = apply_reconciliation(
        [_ent("202610-0838", "sales_order")],
        {"202610-0838": {"sales_order": 1, "customer_order": 1}},
    )
    assert r.kind_pick_options is None
    assert [e["hint"] for e in r.entities] == ["sales_order"]
    assert r.reconciled == []


def test_t15_hinted_exact_kind_wins_without_typed():
    r = apply_reconciliation(
        [_ent("SRTKS8551", "product")],
        {"SRTKS8551": {"product": 1, "promotion": 1}},
        exact={"SRTKS8551": {"product": 1}},
    )
    assert r.kind_pick_options is None
    assert [e["hint"] for e in r.entities] == ["product"]


def test_control_typed_token_without_hinted_exact_hit_still_asks_with_typed():
    r = apply_reconciliation(
        [_ent("Sorento", "brand")],
        {"Sorento": {"transporter": 1, "customer": 1}},
        exact={"Sorento": {"transporter": 1, "customer": 1}},
        typed=_typed("sorento"),
    )
    assert r.kind_pick_options is not None
    assert [o["entity_type"] for o in r.kind_pick_options] == ["customer", "transporter"]
