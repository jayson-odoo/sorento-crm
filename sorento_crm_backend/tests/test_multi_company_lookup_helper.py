"""AC-B6, AC-B7 (and the general shape of AC-A2/A3): direct unit tests for the
shared helper `app.services.company_scope.stamp_lookup_companies`
(PLAN-multi-company-reply-clarity-backend.md section 2).

The helper does not exist yet - this whole file is expected to fail at
COLLECTION with an ImportError until it is added. That is the correct failure
for the TDD red step: "missing helper", not a misbehaving one.
"""
from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import event

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
# (mirrors tests/test_attachment_company_stamp_in_list.py).
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID, stamp_lookup_companies

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as session:
        seed_mocha(session)
        yield session


def _two_company_scope(db) -> None:
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, MOCHA_ID}))


# --- AC-A3 shape: union of product companies and row companies -------------


def test_labels_when_product_ids_span_two_companies_even_with_no_rows(db):
    """AC-B2 shape at the helper level: an empty `rows` list still gets a
    `lookup_companies` label when the resolved product_ids alone span two
    companies."""
    _two_company_scope(db)
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    payload: dict = {"data": []}
    stamp_lookup_companies(
        db, payload, [], product_ids=[p_sorento.id, p_mocha.id]
    )

    assert payload["lookup_companies"] == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_noop_when_product_ids_resolve_to_one_company(db):
    """AC-B4 shape at the helper level: a single-company union touches nothing."""
    _two_company_scope(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    db.commit()

    payload: dict = {"data": []}
    stamp_lookup_companies(db, payload, [], product_ids=[p.id])

    assert "lookup_companies" not in payload


def test_noop_when_no_product_ids_and_no_rows(db):
    _two_company_scope(db)
    payload: dict = {"data": []}
    stamp_lookup_companies(db, payload, [])
    assert "lookup_companies" not in payload


# --- AC-B6: out-of-scope product id contributes nothing ---------------------


def test_out_of_scope_product_id_contributes_nothing(db):
    """A Sorento-only caller passing a Mocha product id must get a
    single-company (unlabelled) answer, never a Mocha label - the scoped ORM
    query silently excludes the Mocha product before the helper ever sees it."""
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    payload: dict = {"data": []}
    stamp_lookup_companies(db, payload, [], product_ids=[p_mocha.id])

    assert "lookup_companies" not in payload


# --- AC-B7: one batched companies query, only when union > 1 ---------------


# The blank test schema renders every table name schema-qualified
# (`FROM zzs_blank_1234_abcd.companies`), so a literal "from companies" match
# never fires here. The word boundary keeps `user_companies` /
# `respond_contact_companies` out.
_COMPANIES_TABLE = re.compile(r"\bcompanies\b")


def _count_companies_queries(db, fn) -> int:
    statements: list[str] = []

    def _capture(conn, cursor, statement, *_a, **_kw):
        if _COMPANIES_TABLE.search(statement.lower()):
            statements.append(statement)

    connection = db.get_bind()
    event.listen(connection, "before_cursor_execute", _capture)
    try:
        fn()
    finally:
        event.remove(connection, "before_cursor_execute", _capture)
    return len(statements)


def test_one_batched_companies_query_when_union_gt_1(db):
    _two_company_scope(db)
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    payload: dict = {"data": []}
    count = _count_companies_queries(
        db,
        lambda: stamp_lookup_companies(
            db, payload, [], product_ids=[p_sorento.id, p_mocha.id]
        ),
    )
    assert count == 1, f"expected exactly one companies query, saw {count}"


def test_no_companies_query_when_union_lte_1(db):
    _two_company_scope(db)
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    db.commit()

    payload: dict = {"data": []}
    count = _count_companies_queries(
        db, lambda: stamp_lookup_companies(db, payload, [], product_ids=[p.id])
    )
    assert count == 0, f"expected no companies query for a single-company union, saw {count}"


# --- row shapes: dict / ORM / row_company_id callable -----------------------


def test_stamps_dict_rows_with_both_keys(db):
    _two_company_scope(db)
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    rows = [{"id": "row-1", "company_id": DEFAULT_COMPANY_ID}]
    payload: dict = {"data": rows}
    stamp_lookup_companies(
        db, payload, rows, product_ids=[p_sorento.id, p_mocha.id]
    )

    assert rows[0]["company_id"] == DEFAULT_COMPANY_ID
    assert rows[0]["company_name"] == "Sorento"
    assert payload["lookup_companies"] == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


def test_stamps_orm_rows_company_name_only(db):
    """An ORM row already has `company_id` (the real column); the helper adds
    only `company_name`."""
    _two_company_scope(db)
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    p_mocha = product(db, company_id=MOCHA_ID)
    db.commit()

    payload: dict = {"data": [p_sorento]}
    stamp_lookup_companies(
        db, payload, [p_sorento], product_ids=[p_sorento.id, p_mocha.id]
    )

    assert p_sorento.company_id == DEFAULT_COMPANY_ID
    assert getattr(p_sorento, "company_name", None) == "Sorento"


def test_row_company_id_callable_for_rows_with_no_company_id_attribute(db):
    """Incoming-stock rows are hand-built dicts whose company lives under a
    different key (e.g. the shipment's company, captured while building the
    row) - `row_company_id` lets the helper find it there instead."""
    _two_company_scope(db)
    p_sorento = product(db, company_id=DEFAULT_COMPANY_ID)
    db.commit()

    rows = [{"shipment_number": "SH1", "_ship_company": MOCHA_ID}]
    payload: dict = {"data": rows}
    stamp_lookup_companies(
        db,
        payload,
        rows,
        product_ids=[p_sorento.id],
        row_company_id=lambda r: r["_ship_company"],
    )

    assert rows[0]["company_id"] == MOCHA_ID
    assert rows[0]["company_name"] == "Mocha"
    assert payload["lookup_companies"] == [
        {"id": MOCHA_ID, "name": "Mocha"},
        {"id": DEFAULT_COMPANY_ID, "name": "Sorento"},
    ]


# --- best-effort: never fatal ------------------------------------------------


def test_best_effort_never_raises_on_bad_product_id(db):
    """A non-UUID product id would blow up a raw `Product.id.in_([...])`
    comparison at the database - the helper must swallow it and leave the
    payload untouched rather than turning an additive label into a 500."""
    _two_company_scope(db)
    payload: dict = {"data": []}

    stamp_lookup_companies(db, payload, [], product_ids=["not-a-uuid"])

    assert "lookup_companies" not in payload
