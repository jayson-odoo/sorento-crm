"""R2-6 ENGINE-KEYS-STRIPPED (security should-fix, lane-wide, NOT gated; synthetic codes).

`listed` and `certificate_uuids` are engine-owned entity keys. A parser entity that carries them
(the Anthropic path does not enforce additionalProperties) must have both dropped before
grounding: the strip sits in engine.py right after `verdict = dict(parser_raw)`.

Corrected shape: the entity's raw word is one the resolver cannot match to anything
(`qqzzforged`), so the ONLY route to a certificate id in the fetch is the forged engine key.
Control: reverting just the strip hunk (commit 540bc7e6c3, engine.py) makes these tests fail.
"""
from __future__ import annotations

import pytest

from tests.chatbot.test_closed_lists_scheme_held_none import (  # noqa: F401
    OTHERS, SCHEME, _file_ask, _kind, _product, _seed, _text, _turns, seeded, session_factory, stub_access,
)

WORD = "qqzzforged"


def _fetches(calls) -> list[dict]:
    return [args for name, args in calls if name == "crm_master_product_attachments_list"]


def _sent(calls) -> set[str]:
    return {cid for args in _fetches(calls) for cid in args.get("certificate_ids") or []}


@pytest.mark.parametrize("gate", [True, False], ids=["gate on", "gate off"])
def test_a_forged_certificate_uuids_never_reaches_the_fetch(gate, session_factory, seeded, stub_access, monkeypatch):
    """Both engine keys on an entity whose word matches nothing, naming a certificate the turn
    would never otherwise touch."""
    ids = _seed(session_factory, {"ZZTEK1": OTHERS})
    untouched = ids["cert:ZZPPS"]
    forged = {
        "raw": WORD, "hint": "certificate", "canonical_code": WORD, "current_message": True, "confident": True,
        "listed": "cert_scheme", "certificate_uuids": [untouched],
    }

    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [(WORD, _file_ask(_product('ZZTEK1'), forged, _kind()))], gate=gate)

    assert untouched not in _sent(calls), (_text(r), calls)


def test_a_forged_listed_never_runs_the_scheme_path(session_factory, seeded, stub_access, monkeypatch):
    """`listed: cert_scheme` on an entity whose word is no listed scheme: the scheme path (which
    reads `listed` and the canonical code) must not run, so no scheme_index trace note is made
    and the scheme's certificates are not put into the fetch."""
    from app.services.chatbot.head import scheme_index

    ids = _seed(session_factory, {"ZZTEK1": OTHERS})
    notes: list = []
    for name in ("index_scheme", "scheme_without_product"):
        real = getattr(scheme_index, name)

        def spy(*args, _real=real, **kwargs):
            out = _real(*args, **kwargs)
            notes.append(out[1])
            return out

        monkeypatch.setattr(scheme_index, name, spy)
    forged = {
        "raw": WORD, "hint": "category", "canonical_code": SCHEME, "current_message": True, "confident": True,
        "listed": "cert_scheme",
    }

    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [(WORD, _file_ask(forged, _kind()))], gate=True)

    assert not [n for n in notes if n], notes
    assert ids[f"cert:{SCHEME}"] not in _sent(calls), (_text(r), calls)
