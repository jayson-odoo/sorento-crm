"""R4-4 CERT-NUMBER-AS-SET (TRAIN cp0-5b20fdfe69 x3; synthetic ZZ data).

"latest certificate of ZZIKRAM ZZ0001FC": the parser hints "ZZIKRAM ZZ0001FC" as a product plus
the certificate kind; the resolver places it exactly as a CERTIFICATE by number (reconciled
product -> certificate), but the set skip only exempted typed PRODUCT codes, so a set was built
from the leftover words and qualified nothing: "Couldn't find: give latest". Rule: a token the
resolver matched exactly as a certificate counts as a typed code, so the fetch carries those
certificate ids (narrowed to a listed scheme when the parser picked one: the same number exists
under another scheme) and the file is sent.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  isort:skip
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

NUMBER = "ZZ0001FC"


def _world(session_factory) -> World:
    w = World(session_factory)
    w.file("ZZP1", type_name="ZZT Certification", cert=True, scheme="ZZIKRAM", number=NUMBER, key="ikram")
    w.file("ZZP2", type_name="ZZT Certification", cert=True, scheme="ZZKMARK", number=NUMBER, key="kmark")
    return w.commit()


def _kind():
    return entity("certificate", "attachment_type", canonical="certificate", listed="ZZT Certification")


@pytest.mark.parametrize("scheme_picked", [False, True], ids=["number only", "listed scheme picked"])
def test_a_certificate_number_is_a_code_the_fetch_carries(scheme_picked, session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)
    ents = [entity(f"ZZIKRAM {NUMBER}", "product"), _kind()]
    if scheme_picked:
        ents.insert(1, entity("ZZIKRAM", "attachment_type", canonical="certificate", listed="ZZIKRAM"))

    [(r, calls)] = run_turns(
        session_factory, stub_access, monkeypatch, [(f"give latest certificate of ZZIKRAM {NUMBER}", real_parse(ents, scope_intent="specific"))], w,
    )

    text = text_of(r)
    assert "Couldn't find" not in text, (text, calls)
    sent = fetches(calls)
    assert sent, (text, calls)
    ids = set(sent[0].get("certificate_ids") or [])
    assert w.certs["ikram"] in ids, sent
    if scheme_picked:
        assert ids == {w.certs["ikram"]}, sent
    assert "ZZP1_ZZIKRAM.pdf" in text, text
