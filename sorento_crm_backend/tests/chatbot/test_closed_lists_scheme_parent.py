"""F3-b ONE PARENTED LIST (crew a29691875, order a30139843; plan "F3-b acceptance" B-1 to B-4; ZZ data).

A certificate scheme has no table and no parent column: its only link to a certificate kind is per
certificate (`certificates.scheme` + `attachment_type_id`). So a scheme's kind is the attachment type
most of its active certificates carry (count first, type name only as a tiebreak), and a scheme no
certificate carries has no kind (B-1). A scheme pick carries that kind on the SAME entity; no separate
kind entity is appended (B-2), and a kind said beside its scheme folds into it when it is the scheme's
parent (B-3). The fetch, the held-none line, the no-product scheme read and the gate-off turn stay as
they are (B-4).

Seed: the full link chain (certificate -> current revision -> attachment -> product_attachments ->
product, plus certificate_products) through `tests/chatbot/_attach_world.World`.
- ZZSPAN: three active certificates filed as "ZZ Test report", one as "ZZ Certificate" (the name that
  sorts first), so its parent by data is ZZ Test report.
- ZZIKR: two certificates, both "ZZ Test report" (one parent whichever way it is read).
- ZZNOREC: a `certificate_scheme` lookup option no certificate carries (lookup only).
"""
from __future__ import annotations

import json
import uuid

import app.main  # noqa: F401  isort:skip
from app.models.lookup import LookupOption, LookupSet
from app.services.chatbot import trace as trace_mod
from tests.chatbot._attach_world import World, entity, fetches, real_parse, run_turns, text_of
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_engine import _parser_output, seeded, stub_access  # noqa: F401

REPORT, CERT = "ZZ Test report", "ZZ Certificate"
#: Attachment types carry a code, as real ones do; the lists print the code.
CODES = {REPORT: "ZZTR", CERT: "ZZCT"}


def _world(session_factory) -> World:
    w = World(session_factory)
    for name, code in CODES.items():
        w.type(name, cert=True, code=code)
    for n, code in enumerate(("ZZSP101", "ZZSP102", "ZZSP103")):
        w.file(code, type_name=REPORT, cert=True, scheme="ZZSPAN", key=f"span-report-{n}")
    w.file("ZZSP104", type_name=CERT, cert=True, scheme="ZZSPAN", key="span-cert")
    w.file("ZZIK201", type_name=REPORT, cert=True, scheme="ZZIKR", key="ikr-1")
    w.file("ZZIK202", type_name=REPORT, cert=True, scheme="ZZIKR", key="ikr-2")
    w.file("ZZPL301", type_name=REPORT, cert=True, scheme="ZZPPL", key="ppl-1")
    lookup = LookupSet(id=str(uuid.uuid4()), set_key="certificate_scheme", name="Certificate Scheme")
    w.db.add(lookup)
    w.db.flush()
    w.db.add(LookupOption(id=str(uuid.uuid4()), set_id=lookup.id, value="ZZNOREC", label="ZZNOREC", sort_order=0, is_active=True))
    return w.commit()


def _scheme(word: str, scheme: str) -> dict:
    return entity(word, "attachment_type", canonical=scheme, listed=scheme)


def _kind(word: str, name: str) -> dict:
    return entity(word, "attachment_type", canonical=name, listed=name)


def _product(code: str) -> dict:
    return entity(code, "product", canonical=code)


def _turns(session_factory, stub_access, monkeypatch, turns, w: World, *, gate: bool = True):
    """[(result, calls, entities of the verdict APPLY read)] per turn."""
    traces: list = []
    real = trace_mod.TurnTrace.persisted
    monkeypatch.setattr(trace_mod.TurnTrace, "persisted", lambda self: (traces.append(real(self)) or traces[-1]))
    out = run_turns(session_factory, stub_access, monkeypatch, turns, w, gate=gate)
    applied = [r for t in traces for r in t if r.get("kind") == "apply"]
    assert len(applied) >= len(turns), [r.get("kind") for t in traces for r in t]
    last = [e for e in (applied[-1].get("verdict") or {}).get("entities") or [] if isinstance(e, dict)]
    return out, last


def _file_entities(entities: list[dict]) -> list[dict]:
    """The file-side entities (the scheme / kind picks, however typed), product rows aside."""
    return [e for e in entities if str(e.get("hint") or "").strip().lower() != "product"]


def _type_ids(w: World, *names: str) -> list[str]:
    return [w.types[n].id for n in names]


# --- reds -----------------------------------------------------------------------------------


def test_p1_a_schemes_kind_is_the_one_most_of_its_certificates_carry(session_factory, seeded, stub_access, monkeypatch):
    """B-1. Fails on HEAD: `_kind_item` orders the scheme's kinds by type name, so the one "ZZ
    Certificate" outranks the three "ZZ Test report" certificates and the fetch asks for that kind."""
    w = _world(session_factory)

    [(r, calls)], _entities = _turns(session_factory, stub_access, monkeypatch, [("zzspan docs pls", real_parse([_scheme("zzspan", "ZZSPAN")]))], w)

    sent = fetches(calls)
    assert sent, (text_of(r), calls)
    assert sent[0].get("attachment_type_ids") == _type_ids(w, REPORT), sent


def test_p2_a_scheme_no_certificate_carries_gets_no_kind(session_factory, seeded, stub_access, monkeypatch):
    """B-1. Fails on HEAD: the lookup-only scheme's kind falls back to the alphabetically first
    listed kind, which `index_scheme` appends beside it."""
    w = _world(session_factory)

    [(_r, _calls)], entities = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzsp101 zznorec cert", real_parse([_product("ZZSP101"), _scheme("zznorec", "ZZNOREC")]))], w,
    )

    said = json.dumps(_file_entities(entities), default=str)
    assert not [k for k in (CERT, REPORT, *CODES.values(), *_type_ids(w, CERT, REPORT)) if k in said], said
    assert not [e for e in entities if e.get("listed") == "cert_kind"], entities


def test_p3_a_scheme_pick_is_one_entity_carrying_its_kind_and_certificates(session_factory, seeded, stub_access, monkeypatch):
    """B-2. Fails on HEAD: R4-2 appends a separate kind entity beside the scheme (two file entities)."""
    w = _world(session_factory)

    [(_r, _calls)], entities = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzik201 zzikr certificate", real_parse([_product("ZZIK201"), _scheme("zzikr", "ZZIKR")]))], w,
    )

    files = _file_entities(entities)
    assert len(files) == 1, files
    assert files[0].get("certificate_uuids") == [w.certs["ikr-1"]], files
    said = json.dumps(files[0], default=str)
    assert any(k in said for k in (REPORT, CODES[REPORT], w.types[REPORT].id)), files  # its parent kind rides on it


def test_p4_a_kind_said_beside_its_own_scheme_folds_into_the_scheme(session_factory, seeded, stub_access, monkeypatch):
    """B-3. Fails on HEAD: the parser's kind entity (the scheme's parent) stays beside the scheme."""
    w = _world(session_factory)

    [(_r, _calls)], entities = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzik201 zzikr test report", real_parse([_product("ZZIK201"), _scheme("zzikr", "ZZIKR"), _kind("test report", REPORT)]))], w,
    )

    assert len(_file_entities(entities)) == 1, entities


# --- guards (pass on HEAD) ------------------------------------------------------------------


def test_guard_a_different_kind_beside_a_scheme_keeps_both(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    [(_r, _calls)], entities = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzik201 zzikr certificate copy", real_parse([_product("ZZIK201"), _scheme("zzikr", "ZZIKR"), _kind("certificate", CERT)]))], w,
    )

    files = _file_entities(entities)
    assert len(files) == 2, files
    assert any(e.get("listed") == "cert_kind" and e.get("canonical_code") == CODES[CERT] for e in files), files
    assert any(e.get("listed") == "cert_scheme" for e in files), files


def test_guard_p3s_fetch_is_unchanged_the_kinds_id_and_the_schemes_certificates(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    [(r, calls)], _entities = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzik201 zzikr certificate", real_parse([_product("ZZIK201"), _scheme("zzikr", "ZZIKR")]))], w,
    )

    sent = fetches(calls)
    assert sent, (text_of(r), calls)
    assert sent[0].get("product_ids") == [w.products["ZZIK201"].id], sent
    assert sent[0].get("attachment_type_ids") == _type_ids(w, REPORT), sent
    assert sent[0].get("certificate_ids") == [w.certs["ikr-1"]], sent


def test_guard_the_held_none_line_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)
    stock = _parser_output(intent_hint="check_stock", domain_hint="inventory", user_goal="stock", entities=[_product("ZZPL301")])

    (_r1, _c1), (r2, _c2) = run_turns(
        session_factory, stub_access, monkeypatch, [("ZZPL301", stock), ("any zzspan one for it", real_parse([_scheme("zzspan", "ZZSPAN")]))], w,
    )

    assert text_of(r2) == "ZZPL301: no ZZSPAN certificate on record.", text_of(r2)


def test_guard_a_scheme_with_no_product_sends_its_own_certificates_bounded(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    [(r, calls)], _entities = _turns(session_factory, stub_access, monkeypatch, [("zzspan docs pls", real_parse([_scheme("zzspan", "ZZSPAN")]))], w)

    sent = fetches(calls)
    assert sent, (text_of(r), calls)
    ids = sent[0].get("certificate_ids") or []
    assert set(ids) == {w.certs[k] for k in ("span-report-0", "span-report-1", "span-report-2", "span-cert")} and len(ids) <= 200, sent


def test_guard_gate_off_the_scheme_turn_is_unchanged(session_factory, seeded, stub_access, monkeypatch):
    w = _world(session_factory)

    [(_r, _calls)], entities = _turns(
        session_factory, stub_access, monkeypatch,
        [("zzik201 zzikr certificate", real_parse([_product("ZZIK201"), _scheme("zzikr", "ZZIKR")]))], w, gate=False,
    )

    # Ungated, the scheme word is no listed document type and grounding drops it, as today.
    assert not [e for e in entities if e.get("certificate_uuids") or e.get("listed")], entities
    assert _file_entities(entities) == [], entities
