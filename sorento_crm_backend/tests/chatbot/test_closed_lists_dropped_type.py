"""R4-3 DROPPED-TYPE-CARRIES-OLD (TRAIN cp0-6240dc53f8, 3 of 9 pooled; synthetic ZZ data).

The previous turn left the file type "ZZ Videos" on the focus. The next message's attachment_type
entity (an unsure pick naming no listed item, or "none of these") is dropped by grounding,
and the old type stayed alive and was fetched. Rule: a current-message attachment_type entity that
grounding drops still REPLACES the type axis with nothing for the turn, so the turn takes the
which-file ask over the product's own types. Gate off: unchanged.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  isort:skip
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401


def _world(session_factory) -> World:
    w = World(session_factory)
    w.file("ZZWC100", type_name="ZZ Videos", key="vid")
    w.file("ZZWC100", type_name="ZZ Drawings", key="drw")
    return w.commit()


def _turns(w: World, second: dict):
    first = real_parse([entity("ZZWC100", "product", canonical="ZZWC100"),
                        entity("videos", "attachment_type", canonical="ZZ Videos", listed="ZZ Videos")])
    return [("ZZWC100 videos", first), ("pdf", second)]


DROPPED = [
    # Owner ruling 20 Oct 2026 on cp0-6240dc53f8 (KEEP, lead sign-off): an unconfident pick whose
    # listed_item is EXACTLY a listed item is kept now, so the unsure case here names no listed item
    # (its canonical_code alone hits one).
    entity("pdf", "attachment_type", canonical="ZZ Drawings", listed=None, confident=False),
    entity("pdf", "attachment_type", canonical="technical drawing", listed="none of these"),
]


@pytest.mark.parametrize("pick", DROPPED, ids=["not confident, not exactly listed", "none of these"])
def test_a_dropped_type_pick_never_answers_with_the_old_type(pick, session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    (_r1, _c1), (r2, c2) = run_turns(session_factory, stub_access, monkeypatch, _turns(w, real_parse([pick], entity_op="reuse")), w)

    videos = w.types["ZZ Videos"].id
    assert not any(videos in (a.get("attachment_type_ids") or []) for a in fetches(c2)), c2
    text = text_of(r2)
    assert "Which kind of file do you need?" in text, text


def test_gate_off_the_old_type_carries_as_before(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)
    pick = DROPPED[0]

    (_r1, _c1), (_r2, c2) = run_turns(session_factory, stub_access, monkeypatch, _turns(w, real_parse([pick], entity_op="reuse")), w, gate=False)

    videos = w.types["ZZ Videos"].id
    assert any(videos in (a.get("attachment_type_ids") or []) for a in fetches(c2)), c2
