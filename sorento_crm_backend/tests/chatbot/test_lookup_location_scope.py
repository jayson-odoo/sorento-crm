"""CHAT-INCOMING-LOCATION-SCOPE, Phase 2 red tests: the parser's LOCATION lookup list under a
contact's location scope. Covers AC-10 (and the None = unchanged half of AC-9).

UAC: documentation/plans/chatbot/chat-incoming-location-scope-acceptance-criteria.md
Plan: documentation/plans/chatbot/PLAN-chat-incoming-location-scope.md (design item 5)

Contract: `lookup_lists._location_rows(db, warehouse_scope)` and
`lookup_lists.load_rows(db, ..., warehouse_scope=...)` return LOCATION rows only for the warehouse
ids in the scope list (still active ones only); `None` = every active warehouse, as today; an
empty list = no location rows. Tested at function level; the engine's wiring of the resolved
contact's scope is not covered here.

Postgres only, blank schema, every row seeded here.
"""
from __future__ import annotations

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.base import set_company_scope
from app.services.chatbot.head import lookup_lists as ll
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import warehouse
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _world(db):
    brw = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("BRW")[:20])
    bb = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=f"{brw.warehouse_code}-BB")
    mwh = warehouse(db, company_id=DEFAULT_COMPANY_ID, code=unique_code("MWH")[:20])
    db.flush()
    return brw, bb, mwh


def _codes(rows):
    return {r.label.rsplit("(", 1)[-1].rstrip(")") for r in rows if r.list_name == "location"}


def test_ac10_location_rows_are_only_the_scope_warehouses(db):
    brw, bb, mwh = _world(db)
    rows = ll._location_rows(db, [str(brw.id), str(mwh.id)])
    assert _codes(rows) == {brw.warehouse_code, mwh.warehouse_code}


def test_ac10_load_rows_passes_the_scope_to_the_location_list(db):
    brw, bb, mwh = _world(db)
    rows = ll.load_rows(db, warehouse_scope=[str(brw.id), str(mwh.id)])
    assert _codes(rows) == {brw.warehouse_code, mwh.warehouse_code}
    assert bb.warehouse_code not in {r.label for r in rows}


def test_ac10_an_inactive_warehouse_in_scope_is_still_not_offered(db):
    brw, bb, mwh = _world(db)
    mwh.is_active = False
    db.flush()
    assert _codes(ll._location_rows(db, [str(brw.id), str(mwh.id)])) == {brw.warehouse_code}


def test_ac10_an_empty_scope_offers_no_location(db):
    _world(db)
    assert ll._location_rows(db, []) == []
    assert not [r for r in ll.load_rows(db, warehouse_scope=[]) if r.list_name == "location"]


def test_ac9_no_scope_offers_every_active_warehouse_as_today(db):
    """Guard: passes before the change."""
    brw, bb, mwh = _world(db)
    expected = {brw.warehouse_code, bb.warehouse_code, mwh.warehouse_code}
    assert expected <= _codes(ll.load_rows(db))
    assert expected <= _codes(ll._location_rows(db))


def test_ac9_scope_none_means_no_filter(db):
    brw, bb, mwh = _world(db)
    expected = {brw.warehouse_code, bb.warehouse_code, mwh.warehouse_code}
    assert expected <= _codes(ll._location_rows(db, None))
    assert expected <= _codes(ll.load_rows(db, warehouse_scope=None))
