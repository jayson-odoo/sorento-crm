"""R4-5 NO-FREE-REMAINDER-ON-FILE-ASK (TRAIN cp0-5c93483505 r1; synthetic ZZ data).

"Request ZZBRAND cert": brand + certificate kind built a set described by the leftover message
word ("request"), which qualified nothing: "Couldn't find: \"request\"". Rule: under the gate, on a
file ask (domain_hint product_attachment) the set is described only by parser entities, never by
leftover message words. Gate off: unchanged.
"""
from __future__ import annotations

import app.main  # noqa: F401  isort:skip
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401


def _world(session_factory) -> World:
    w = World(session_factory)
    w.file("ZZB1P1", type_name="ZZT Certification", cert=True, scheme="ZZSIRIM", brand="ZZBRAND", key="a")
    w.file("ZZB1P2", type_name="ZZT Certification", cert=True, scheme="ZZSIRIM", brand="ZZBRAND", key="b")
    w.file("ZZOTHER1", type_name="ZZT Certification", cert=True, scheme="ZZSIRIM", brand="ZZELSE", key="c")
    return w.commit()


def _ask():
    return real_parse([
        entity("ZZBRAND", "brand", canonical="ZZBRAND"),
        entity("cert", "attachment_type", canonical="certificate", listed="ZZT Certification"),
    ])


def test_a_leftover_word_never_describes_the_set_on_a_file_ask(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    [(r, calls)] = run_turns(session_factory, stub_access, monkeypatch, [("Request ZZBRAND cert", _ask())], w)

    text = text_of(r)
    assert "Couldn't find" not in text, (text, calls)
    assert fetches(calls), (text, calls)
    assert "ZZB1P1_ZZSIRIM.pdf" in text and "ZZB1P2_ZZSIRIM.pdf" in text, text
    assert "ZZOTHER1" not in text, text


def test_gate_off_the_leftover_word_still_describes_the_set(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    [(r, calls)] = run_turns(session_factory, stub_access, monkeypatch, [("Request ZZBRAND cert", _ask())], w, gate=False)

    assert "Couldn't find" in text_of(r), (text_of(r), calls)


def _spy_bodies(monkeypatch) -> list[dict]:
    from app.services.chatbot.lanes.business import resolve_gate

    bodies: list[dict] = []
    real = resolve_gate.resolve_entity_body

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        bodies.append(out)
        return out

    monkeypatch.setattr(resolve_gate, "resolve_entity_body", spy)
    return bodies


def test_a_spec_domain_set_ask_keeps_its_remainder(session_factory, seeded, stub_access, monkeypatch):
    """Reviewer guard: the same leftover-word shape on a product-search (spec slice) domain is not a
    file ask, so `no_free_remainder` is not set and the resolve body is built as before."""
    w = _world(session_factory)
    bodies = _spy_bodies(monkeypatch)
    spec_ask = real_parse(
        [entity("ZZBRAND", "brand", canonical="ZZBRAND"), entity("zz", "category")],
        domain_hint="inventory", intent_hint="check_stock", scope_intent="specific",
    )

    run_turns(session_factory, stub_access, monkeypatch, [("Request ZZBRAND zz stock", spec_ask)], w)
    spec_bodies = [b for b in bodies if "require" in b]

    assert spec_bodies, "the spec-domain ask must reach the set path (a `require` body)"
    assert not any(b.get("no_free_remainder") for b in spec_bodies), spec_bodies
