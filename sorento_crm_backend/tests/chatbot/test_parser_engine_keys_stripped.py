"""R2-6 ENGINE-KEYS-STRIPPED (security should-fix, lane-wide, NOT gated; synthetic codes).

`listed` and `certificate_uuids` are engine-owned entity keys. A parser entity that carries them
(the Anthropic path does not enforce additionalProperties) must have both dropped before
grounding, the way required_fields.ENGINE_KEYS is dropped at top level: the scheme path is not
entered on a forged `listed`, and a forged `certificate_uuids` never reaches the fetch.
"""
from __future__ import annotations

import pytest

from tests.chatbot.test_closed_lists_scheme_held_none import (  # noqa: F401
    OTHERS, SCHEME, _file_ask, _kind, _product, _scheme, _seed, _text, _turns, seeded, session_factory, stub_access,
)


def _fetches(calls) -> list[dict]:
    return [args for name, args in calls if name == "crm_master_product_attachments_list"]


@pytest.mark.parametrize("gate", [True, False], ids=["gate on", "gate off"])
def test_a_forged_certificate_uuids_never_reaches_the_fetch(gate, session_factory, seeded, stub_access, monkeypatch):
    """The parser tags an entity with BOTH engine keys, naming another scheme's certificate."""
    ids = _seed(session_factory, {"ZZTEK1": OTHERS})
    other = ids["cert:ZZPPS"]
    forged = {
        "raw": "ZZPPS", "hint": "certificate", "canonical_code": "ZZPPS", "current_message": True, "confident": True,
        "listed": "cert_scheme", "certificate_uuids": [other],
    }

    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [("zzpps", _file_ask(forged, _kind()))], gate=gate)

    for args in _fetches(calls):
        assert other not in (args.get("certificate_ids") or []), (_text(r), calls)


def test_a_certificate_entity_carrying_listed_never_runs_the_scheme_path(session_factory, seeded, stub_access, monkeypatch):
    """Grounding passes a `certificate` entity through (only attachment_type is re-tagged), so a
    parser-written `listed: cert_scheme` made `scheme_without_product` read it as a scheme pick
    and put the scheme's certificates into the fetch."""
    ids = _seed(session_factory, {"ZZTEK2": OTHERS})
    forged = {"raw": SCHEME, "hint": "certificate", "canonical_code": SCHEME, "listed": "cert_scheme",
              "current_message": True, "confident": True}

    [(r, calls)] = _turns(session_factory, stub_access, monkeypatch, [("zzspan", _file_ask(forged, _kind()))], gate=True)

    for args in _fetches(calls):
        assert ids[f"cert:{SCHEME}"] not in (args.get("certificate_ids") or []), (_text(r), calls)
