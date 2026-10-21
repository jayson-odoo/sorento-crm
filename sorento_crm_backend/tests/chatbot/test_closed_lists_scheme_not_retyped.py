"""R4-2 SCHEME-NO-PRODUCT-RETYPED (TRAIN cp0-fce51f2811 x3; synthetic ZZ data).

Turn 1 is a certificate ask on an unknown code (a did-you-mean product pick stays open, the
Certification type is held). Turn 2 is "Span": one attachment_type entity (canonical
`certificate`, or none), listed_item the scheme. The scheme certificates were found, but the
scheme row was retyped to a certificate, the held Certification type dropped, and the bot asked
"Which kind of file do you need?" with nothing fetched. Rule: the certificate kind is added beside
the scheme, so the company's scheme certificates are fetched with the kind, no product, and the
files are sent.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  isort:skip
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

SCHEME = "ZZSPAN"


def _world(session_factory) -> World:
    w = World(session_factory)
    for code in ("ZZCWC609-RL", "ZZCWC601", "ZZCWC602"):
        w.product(code)
    w.file("ZZSPANP1", type_name="ZZT Certification", cert=True, scheme=SCHEME, key="span1")
    w.file("ZZSPANP2", type_name="ZZT Certification", cert=True, scheme=SCHEME, key="span2")
    w.file("ZZOTHERP1", type_name="ZZT Certification", cert=True, scheme="ZZPPS", key="pps1")
    return w.commit()


def _turn1():
    cert = entity("certificate", "attachment_type", canonical="certificate", listed="ZZT Certification")
    return ("ZZCWC605-RL certificate", real_parse([entity("ZZCWC605-RL", "product"), cert]))


@pytest.mark.parametrize("canonical", ["certificate", None], ids=["canonical certificate", "canonical none"])
def test_a_scheme_pick_after_an_unknown_code_fetches_the_schemes_certificates(canonical, session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)
    pick = entity("Span", "attachment_type", canonical=canonical, listed=SCHEME)

    (_r1, _c1), (r2, c2) = run_turns(session_factory, stub_access, monkeypatch, [_turn1(), ("Span", real_parse([pick]))], w)

    text = text_of(r2)
    assert "Which kind of file" not in text, (text, c2)
    sent = fetches(c2)
    assert sent, (text, c2)
    args = sent[0]
    assert set(args.get("certificate_ids") or []) == {w.certs["span1"], w.certs["span2"]}, sent
    assert w.types["ZZT Certification"].id in (args.get("attachment_type_ids") or []), sent
    assert not args.get("product_ids"), sent
    assert "ZZSPANP1_ZZSPAN.pdf" in text and "ZZSPANP2_ZZSPAN.pdf" in text, text
    assert "ZZOTHERP1" not in text, text
