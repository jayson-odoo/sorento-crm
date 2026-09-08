"""AC-3 (chatbot-warehouse-entity-and-last-in): warehouse resolution is EXACT normalized
code, never prefix / fuzzy fan-out.

`documentation/plans/chatbot/PLAN-chatbot-warehouse-entity-and-last-in.md`;
`chatbot-warehouse-entity-and-last-in-acceptance-criteria.md` AC-3. Owner ruling verbatim,
8 Sep 2026: "it is actually the bare code, so it should be exact match ... brw ib, brwib
should map to brw-ib, but when we say brw, it means brw, not the rest".
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import company_scope
from app.models.inventory import Warehouse
from app.services import entity_resolver as er
from tests._pg_fixture import blank_session

SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _seed_warehouses(db) -> dict[str, str]:
    """Seed `BRW`, `BRW-IB`, `BRW-IR` and return `{code: id}`."""
    ids: dict[str, str] = {}
    for code in ("BRW", "BRW-IB", "BRW-IR"):
        wid = _uid()
        db.add(Warehouse(id=wid, warehouse_code=code, warehouse_name=f"{code} warehouse"))
        ids[code] = wid
    db.flush()
    return ids


def _ids(hits) -> set[str]:
    return {h.uuid for h in hits if h.uuid}


@pytest.mark.parametrize(
    "token, expected_code",
    [
        ("brw", "BRW"),
        ("BRW", "BRW"),
        ("brw ib", "BRW-IB"),
        ("brwib", "BRW-IB"),
        ("brw-ib", "BRW-IB"),
        ("Brw_IB", "BRW-IB"),
    ],
)
def test_exact_normalized_code_resolves_to_exactly_one_match(db, token, expected_code):
    ids = _seed_warehouses(db)
    with company_scope(db, frozenset({SORENTO})):
        hits = er._probe_warehouse(db, [token])[token]
    assert _ids(hits) == {ids[expected_code]}


def test_brw_never_returns_brw_ib_or_brw_ir(db):
    ids = _seed_warehouses(db)
    with company_scope(db, frozenset({SORENTO})):
        hits = er._probe_warehouse(db, ["brw"])["brw"]
    hit_ids = _ids(hits)
    assert ids["BRW-IB"] not in hit_ids
    assert ids["BRW-IR"] not in hit_ids


def test_no_such_code_is_a_miss(db):
    _seed_warehouses(db)
    with company_scope(db, frozenset({SORENTO})):
        hits = er._probe_warehouse(db, ["brw xx"])["brw xx"]
    assert hits == []


def test_prefix_probe_does_not_fan_out_for_a_bare_prefix(db):
    """The Tier-2 slot must not surface BRW-IB/BRW-IR for a token that is only a prefix
    of them and not itself an exact code."""
    ids = _seed_warehouses(db)
    with company_scope(db, frozenset({SORENTO})):
        hits = er._prefix_probe_warehouse(db, "brw")
    assert _ids(hits) == {ids["BRW"]}


def test_and_probe_does_not_fan_out(db):
    ids = _seed_warehouses(db)
    with company_scope(db, frozenset({SORENTO})):
        hits = er._and_probe_warehouse(db, ["brw"])
    assert _ids(hits) == {ids["BRW"]}


def test_inactive_warehouse_still_resolves(db):
    wid = _uid()
    db.add(
        Warehouse(id=wid, warehouse_code="BRW-OLD", warehouse_name="BRW OLD", is_active=False)
    )
    db.flush()
    with company_scope(db, frozenset({SORENTO})):
        hits = er._probe_warehouse(db, ["brw old"])["brw old"]
    assert _ids(hits) == {wid}
