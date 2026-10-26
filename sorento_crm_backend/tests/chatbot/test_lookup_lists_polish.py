"""CHAT-SLIM-INDEX polish round, red tests.

1. `render` caps a label at 120 chars but a Spec label keeps its closing "(key: value)" bracket (the visible part shrinks).
2. Yes/no words and said-in-words number words come from the registry's merged synonyms
   (`product_spec_registry.merged_synonyms`, product_spec_registry.py:1694: seed + staff additions, then
   `suppressed_synonyms` {value: [words]} removed LAST, :1722). A word staff suppressed is not offered; an unsuppressed one is.
   Seeds: `is_frameless` (seed {"true": ["frameless", ...]}), `bowl_count` (seed "2": ["double bowl", ...]).
Postgres only, fake products (Zz prefix).
"""
from __future__ import annotations

import uuid

import app.main  # noqa: F401  isort:skip
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.chatbot.head import lookup_lists as ll
from tests.chatbot._attach_world import World
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_lookup_lists_s2 import scoped


def test_a_capped_spec_label_keeps_its_key_value_bracket():
    label = "ZZ Capacity of the very long named tank " + "x" * 300 + " (zz_capacity: 10)"
    hit = ll.Hit(ll.LookupRow("spec", "k", label, (label,)), "x", 1.0, 0.0)
    line = ll.render({"spec": [hit]})[1]
    assert line.startswith("- ZZ Capacity") and line.endswith("(zz_capacity: 10)"), line
    assert len(line) - 2 <= 120, len(line)


def _seed(session_factory) -> None:
    db = session_factory()
    db.add_all([
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="is_frameless", label="Frameless", data_type="boolean", allowed_values=[],
                            synonyms={"true": ["frameless"]}, suppressed_synonyms={"true": ["borderless"]}, value_labels={}),
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="bowl_count", label="Number of bowls", data_type="numeric",
                            synonyms={"_self": ["bowl", "bowls"], "2": ["double bowl"], "3": ["3 bowl"]},
                            suppressed_synonyms={"3": ["triple bowl"]}),
    ])
    db.commit()
    w = World(session_factory)
    p = w.product("ZZPOL1")
    w.db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=p.id, values={"is_frameless": {"value": True}, "bowl_count": {"value": 2}}))
    w.commit()


def _labels(session_factory, message: str) -> list[str]:
    hits = ll.shortlist(message, ll.load_rows(scoped(session_factory)), None)
    return [h.row.label for h in hits.get("spec", [])]


def test_a_suppressed_yes_no_word_is_not_offered_and_an_unsuppressed_one_is(session_factory):
    _seed(session_factory)
    assert any(ln.endswith("(is_frameless: true)") for ln in _labels(session_factory, "frameless mirror"))
    assert not any("is_frameless" in ln for ln in _labels(session_factory, "borderless mirror")), "a suppressed word was offered"


def test_a_suppressed_number_word_is_not_offered_and_an_unsuppressed_one_is(session_factory):
    _seed(session_factory)
    assert any(ln.endswith("(bowl_count: 2)") for ln in _labels(session_factory, "double bowl sink"))
    assert not any(ln.endswith("(bowl_count: 3)") for ln in _labels(session_factory, "triple bowl sink")), "a suppressed word was offered"
