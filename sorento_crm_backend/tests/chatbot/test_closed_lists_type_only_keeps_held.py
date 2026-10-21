"""R6-4 TYPE-ONLY-KEEPS-HELD (TYPE-ONLY-EMPTY-SET; TRAIN cp0-95b4db8902, cp0-6240dc53f8; ZZ data).

A type-only follow-up ("need the TD file pls": one attachment_type entity, no product, no echo of the
held product) was read as a new ask and the held product was dropped, so the set path ran over many
products. Rule: when every current-message entity is an attachment_type, the held product stays and
its file of that type is fetched; the decision may stay a new ask. A new product or a category in the
message still drops the held product.
"""
from __future__ import annotations

import app.main  # noqa: F401  isort:skip
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

TD = "ZZ Technical Drawing"


def _world(session_factory) -> World:
    w = World(session_factory)
    for code in ("ZZWC200", "ZZWC300", "ZZWC400", "ZZWC500"):
        w.file(code, type_name=TD, category="ZZ Basin")
    return w.commit()


def _held_turn():
    return ("ZZWC200 photo", real_parse([entity("ZZWC200", "product", canonical="ZZWC200")]))


def _td():
    return entity("TD", "attachment_type", canonical="technical drawing", listed=TD)



def _run(session_factory, stub_access, monkeypatch, w, ents):
    return run_turns(session_factory, stub_access, monkeypatch, [_held_turn(), ("need the TD file pls", real_parse(ents))], w)


def test_a_type_only_follow_up_keeps_the_held_product_and_fetches_its_file(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    (_r1, _c1), (r2, c2) = _run(session_factory, stub_access, monkeypatch, w, [_td()])

    sent = fetches(c2)
    assert sent, (text_of(r2), c2)
    assert all(a.get("product_ids") == [w.products["ZZWC200"].id] for a in sent), c2
    assert "ZZWC200_ZZ_Technical_Drawing.pdf" in text_of(r2), text_of(r2)
    assert "ZZWC300" not in text_of(r2), text_of(r2)


def test_guard_a_new_product_in_the_message_drops_the_held_one(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    (_r1, _c1), (r2, c2) = _run(
        session_factory, stub_access, monkeypatch, w, [entity("ZZWC300", "product", canonical="ZZWC300"), _td()],
    )

    ids = {pid for a in fetches(c2) for pid in a.get("product_ids") or []}
    assert w.products["ZZWC300"].id in ids and w.products["ZZWC200"].id not in ids, (text_of(r2), c2)


def test_guard_a_category_in_the_message_drops_the_held_one(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    (_r1, _c1), (r2, c2) = _run(
        session_factory, stub_access, monkeypatch, w, [entity("ZZ Basin", "category"), _td()],
    )

    ids = {pid for a in fetches(c2) for pid in a.get("product_ids") or []}
    assert w.products["ZZWC200"].id not in ids or len(ids) > 1, (text_of(r2), c2)
