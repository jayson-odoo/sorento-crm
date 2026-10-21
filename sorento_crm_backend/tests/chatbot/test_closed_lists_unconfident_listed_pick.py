"""Owner ruling 20 Oct 2026 ~07:40 on cp0-6240dc53f8: KEEP. An attachment pick the parser marks
confident=false whose `listed_item` is EXACTLY an item the lists render is kept, with no ask (the
TRAIN case: the parser picked the right listed item for "pdf" but said it was unsure). Grounding
dropped every unconfident pick (head/grounding.py `_on_closed_lists`), the turn set `dropped_kinds`,
apply cleared the type axis and the reply was "Which kind of file do you need?".

Still dropped and asked: `listed_item` "none of these", or null / not exactly a listed item (a hit
only through `canonical_code` or an alias keyword). Confident picks and the gate-off turn are
unchanged. ZZ data, fresh paraphrases; the attachment types carry codes as real ones do (the
lists print the code).
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  isort:skip
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

CODE = "ZZWC300"
DRAWINGS, DRAWINGS_CODE = "ZZ Drawings", "zz_drawings"
CERTS, CERTS_CODE = "ZZ Certification", "zz_certification"
ASK = "Which kind of file do you need?"


def _world(session_factory) -> World:
    w = World(session_factory)
    w.type(DRAWINGS, code=DRAWINGS_CODE)
    w.type(CERTS, cert=True, code=CERTS_CODE)
    w.file(CODE, type_name=DRAWINGS, key="drw")
    w.file(CODE, type_name=CERTS, cert=True, scheme="ZZSIRIM", key="cert")
    w.file(CODE, type_name="ZZ Videos", key="vid")
    return w.commit()


def _pick(word: str, listed: str | None, *, canonical: str | None = None, confident: bool = False) -> dict:
    return entity(word, "attachment_type", canonical=canonical, listed=listed, confident=confident)


def _turn(session_factory, stub_access, monkeypatch, w: World, message: str, pick: dict, *, gate: bool = True):
    [(r, calls)] = run_turns(
        session_factory, stub_access, monkeypatch,
        [(message, real_parse([entity(CODE, "product", canonical=CODE), pick]))], w, gate=gate,
    )
    return text_of(r), fetches(calls)


# --- reds ------------------------------------------------------------------------------------


def test_k1_an_unconfident_pick_exactly_a_listed_file_type_is_kept(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    text, sent = _turn(session_factory, stub_access, monkeypatch, w, "zzwc300 the layout pdf?", _pick("layout pdf", DRAWINGS_CODE))

    assert ASK not in text, text
    assert sent and all(a.get("attachment_type_ids") == [w.types[DRAWINGS].id] for a in sent), sent
    assert f"{CODE}_{DRAWINGS}.pdf".replace(" ", "_") in text, text


def test_k2_an_unconfident_pick_exactly_a_listed_certificate_kind_is_kept(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    text, sent = _turn(session_factory, stub_access, monkeypatch, w, "zzwc300 approval paper?", _pick("approval paper", CERTS_CODE))

    assert ASK not in text, text
    assert sent and w.types[CERTS].id in (sent[0].get("attachment_type_ids") or []), sent
    assert f"{CODE}_ZZSIRIM.pdf" in text, text


# --- guards (pass on HEAD) -------------------------------------------------------------------


NOT_EXACT = [
    pytest.param(_pick("layout pdf", "none of these", canonical=DRAWINGS_CODE), id="none of these"),
    pytest.param(_pick("layout pdf", None, canonical=DRAWINGS_CODE), id="listed null, canonical hit only"),
    pytest.param(_pick("layout pdf", DRAWINGS, canonical=None), id="listed the name, not the listed code"),
]


@pytest.mark.parametrize("pick", NOT_EXACT)
def test_guard_an_unconfident_pick_not_exactly_listed_is_still_dropped_and_asked(pick, session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    text, sent = _turn(session_factory, stub_access, monkeypatch, w, "zzwc300 the layout pdf?", pick)

    assert ASK in text, text
    assert not any(w.types[DRAWINGS].id in (a.get("attachment_type_ids") or []) for a in sent), sent


def test_guard_a_confident_exact_pick_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    text, sent = _turn(session_factory, stub_access, monkeypatch, w, "zzwc300 the layout pdf?", _pick("layout pdf", DRAWINGS_CODE, confident=True))

    assert ASK not in text, text
    assert sent and sent[0].get("attachment_type_ids") == [w.types[DRAWINGS].id], sent


def test_guard_gate_off_the_unconfident_pick_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    """Ungated, the pick is read as before (a confident listed document type only), so this
    unsure pick is no document type and the file ask is the one HEAD gives."""
    w = _world(session_factory)

    text, _sent = _turn(session_factory, stub_access, monkeypatch, w, "zzwc300 the layout pdf?", _pick("layout pdf", DRAWINGS_CODE), gate=False)

    assert ASK in text, text
