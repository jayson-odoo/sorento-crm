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
