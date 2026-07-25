"""Company-scope enforcement tests (multi-company data isolation).

Security core — Group H of UAC-multi-company-isolation.md:
  - AC-H1 leak test: UNSET -> 0 rows; single-company scope -> only that company;
    None -> all companies (across a representative set of owned models).
  - AC-H2 new-table guard: every model with a company_id column is a
    CompanyScopedMixin subclass (except the M2M grant/membership tables).
  - AC-H3 four-state predicate: UNSET/empty -> false(), None -> no predicate,
    frozenset -> IN (...); empty never renders `.in_([])`.
  - AC-H5 attachments: shared (null) rows always visible; owned rows scoped.
  - AC-D4: a system write (scope None/UNSET) to an owned table without a
    company_id is rejected (never inserts a null-company owned row).

Runs against the local Postgres dev DB (a prod-copy) inside a nested transaction
that is ALWAYS rolled back, so no real data is created. All test rows carry a
``zzscope-<suffix>`` / ``ZZSCOPE`` marker and are scoped by the two throwaway test
company ids — no unscoped DELETE (the DB is the developer's real data).
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import false as sa_false
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.database import SessionLocal, Base
from app.models.base import CompanyScopedMixin
from app.models.company import Company
from app.models.product import Brand, ProductCategory
from app.models.inventory import Warehouse
from app.models.marketing import CampaignType
from app.models.order import Transporter
from app.models.resources import Attachment, AttachmentDirectory
from app.services.company_scope import (
    UNSET,
    build_company_predicate,
    company_scope,
    register_company_scope_listeners,
)
from app.services.error_handler import AppException

# The scope listeners are normally installed at import time by app.main / the
# worker path; install them explicitly so this file is self-contained.
register_company_scope_listeners()


@pytest.fixture(autouse=True)
def _strict_owned_insert():
    """This module asserts the REAL enforcement (fail-closed rejection + auto-stamp),
    so it opts out of the conftest ``_TEST_LEAVE_NULL_OWNED_INSERT`` legacy escape
    (which lets owned inserts leave company_id null). Restore it afterwards so the
    rest of the suite keeps its pre-isolation behaviour."""
    import app.services.company_scope as _cs

    prev = _cs._TEST_LEAVE_NULL_OWNED_INSERT
    _cs._TEST_LEAVE_NULL_OWNED_INSERT = False
    try:
        yield
    finally:
        _cs._TEST_LEAVE_NULL_OWNED_INSERT = prev

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

# Owned models exercised in the leak test — one per model file, none with
# __audit_track__ (keeps the flush free of audit side effects).
REPRESENTATIVE = [
    (Brand, "brand_code", dict(brand_name="ZZSCOPE brand")),
    (Warehouse, "warehouse_code", dict(warehouse_name="ZZSCOPE wh")),
    (CampaignType, "type_code", dict(type_name="ZZSCOPE ct")),
    (ProductCategory, "category_code", dict(category_name="ZZSCOPE cat")),
]


def _compile(expr) -> str:
    if expr is None:
        return "<none>"
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def data(db: Session):
    """Two throwaway companies (A, B) + one owned row of each representative model
    per company, plus attachments (company A / company B / shared-null)."""
    suffix = uuid.uuid4().hex[:8]
    company_a = Company(id=str(uuid.uuid4()), name=f"ZZSCOPE A {suffix}", code=f"ZA{suffix}")
    company_b = Company(id=str(uuid.uuid4()), name=f"ZZSCOPE B {suffix}", code=f"ZB{suffix}")
    db.add_all([company_a, company_b])
    db.flush()
    a, b = company_a.id, company_b.id

    for model, code_field, extra in REPRESENTATIVE:
        for company_id in (a, b):
            kwargs = dict(extra)
            uniq = f"ZZSCOPE-{code_field}-{company_id[:6]}-{suffix}"
            kwargs[code_field] = uniq
            # Some name columns carry their own UNIQUE constraint (e.g.
            # campaign_types.type_name); make every *_name unique per row.
            for k in list(kwargs):
                if k.endswith("_name"):
                    kwargs[k] = f"{kwargs[k]} {uniq}"
            kwargs["company_id"] = company_id
            if model is Transporter:  # unused here but kept generic
                kwargs["normalized_name"] = uniq.lower()
            db.add(model(**kwargs))
    # AttachmentDirectory (owned) for A and B
    db.add(AttachmentDirectory(name=f"ZZSCOPE dir {suffix}", company_id=a))
    db.add(AttachmentDirectory(name=f"ZZSCOPE dir {suffix}", company_id=b))

    # Attachments: A / B / shared(null).
    fname = f"zzscope-{suffix}"
    for tag, company_id in (("a", a), ("b", b), ("shared", None)):
        att = Attachment(
            original_filename=f"{fname}-{tag}.pdf",
            stored_filename=f"{fname}-{tag}.pdf",
            file_path=f"/zzscope/{fname}-{tag}.pdf",
            company_id=company_id,
        )
        db.add(att)
    db.flush()
    return {"a": a, "b": b, "suffix": suffix, "fname": fname}


# --- AC-H1 leak test -----------------------------------------------------------
@pytest.mark.parametrize("model,code_field", [(m, f) for m, f, _ in REPRESENTATIVE])
def test_unset_scope_returns_zero_rows(db, data, model, code_field):
    ids = [data["a"], data["b"]]
    with company_scope(db, UNSET):
        count = db.query(model).filter(model.company_id.in_(ids)).count()
    assert count == 0, f"{model.__name__} leaked under UNSET (fail-closed expected)"


@pytest.mark.parametrize("model,code_field", [(m, f) for m, f, _ in REPRESENTATIVE])
def test_single_company_scope_returns_only_that_company(db, data, model, code_field):
    ids = [data["a"], data["b"]]
    with company_scope(db, frozenset({data["a"]})):
        rows = db.query(model).filter(model.company_id.in_(ids)).all()
    assert len(rows) == 1
    assert rows[0].company_id == data["a"]


@pytest.mark.parametrize("model,code_field", [(m, f) for m, f, _ in REPRESENTATIVE])
def test_none_scope_returns_all_companies(db, data, model, code_field):
    ids = [data["a"], data["b"]]
    with company_scope(db, None):
        count = db.query(model).filter(model.company_id.in_(ids)).count()
    assert count == 2


def test_empty_scope_returns_zero_rows(db, data):
    ids = [data["a"], data["b"]]
    with company_scope(db, frozenset()):
        count = db.query(Brand).filter(Brand.company_id.in_(ids)).count()
    assert count == 0


# --- M2 statement-cache cross-scope isolation ---------------------------------
def test_back_to_back_single_scopes_do_not_leak_via_statement_cache(db, data):
    """Same session/engine, two single-company scopes of IDENTICAL cardinality
    (``IN (:one)``) executed back-to-back. The scope predicate is injected as a
    CONCRETE clause (not a lambda), so each scope's company id is part of the
    statement-cache key and the second query must NOT reuse the first scope's
    baked value. Guards the with_loader_criteria/statement-cache same-cardinality
    leak that a lambda predicate would silently cause."""
    ids = [data["a"], data["b"]]
    # Run twice interleaved to exercise a warmed cache (A, B, A, B).
    for _ in range(2):
        with company_scope(db, frozenset({data["a"]})):
            rows_a = db.query(Brand).filter(Brand.company_id.in_(ids)).all()
        with company_scope(db, frozenset({data["b"]})):
            rows_b = db.query(Brand).filter(Brand.company_id.in_(ids)).all()
        assert {r.company_id for r in rows_a} == {data["a"]}, "scope B leaked into A's read"
        assert {r.company_id for r in rows_b} == {data["b"]}, "scope A leaked into B's read"


# --- AC-H5 attachments (shared) ------------------------------------------------
def _att_query(db, fname):
    return db.query(Attachment).filter(Attachment.original_filename.like(f"{fname}-%"))


def test_attachments_unset_shows_only_shared(db, data):
    with company_scope(db, UNSET):
        rows = _att_query(db, data["fname"]).all()
    assert {r.company_id for r in rows} == {None}


def test_attachments_single_company_shows_owned_plus_shared(db, data):
    with company_scope(db, frozenset({data["a"]})):
        rows = _att_query(db, data["fname"]).all()
    got = {r.company_id for r in rows}
    assert got == {data["a"], None}
    assert data["b"] not in got


def test_attachments_none_shows_all(db, data):
    with company_scope(db, None):
        rows = _att_query(db, data["fname"]).all()
    assert {r.company_id for r in rows} == {data["a"], data["b"], None}


# --- AC-H3 four-state predicate ------------------------------------------------
def test_predicate_none_adds_nothing():
    assert build_company_predicate(Brand, None) is None


def test_predicate_unset_is_false_for_owned():
    sql = _compile(build_company_predicate(Brand, UNSET)).lower()
    assert "false" in sql
    assert "in ()" not in sql


def test_predicate_empty_frozenset_is_false_not_empty_in():
    sql = _compile(build_company_predicate(Brand, frozenset())).lower()
    assert "false" in sql
    assert "in ()" not in sql  # never the .in_([]) footgun


def test_predicate_frozenset_is_in_clause():
    cid = str(uuid.uuid4())
    sql = _compile(build_company_predicate(Brand, frozenset({cid}))).lower()
    assert "company_id in" in sql
    # UUID literals render dash-stripped by the pg dialect; compare normalized.
    assert cid.replace("-", "") in sql.replace("-", "")


def test_predicate_attachment_shared_null_or_in():
    cid = str(uuid.uuid4())
    sql = _compile(build_company_predicate(Attachment, frozenset({cid}))).lower()
    assert "is null" in sql
    assert "company_id in" in sql


def test_predicate_attachment_unset_is_null_only():
    sql = _compile(build_company_predicate(Attachment, UNSET)).lower()
    assert "is null" in sql
    assert "false" not in sql  # shared rows still visible under fail-closed


# --- AC-H2 new-table guard -----------------------------------------------------
# Tables that legitimately carry a company_id column WITHOUT being owned/partitioned:
#   - M2M grant/membership tables (shared bucket).
#   - Infra/pipeline tables that snapshot a company_id but are NOT auto-filtered by
#     the ORM listener: import_jobs (enqueue snapshot, worker re-establishes scope);
#     embedding_documents / embedding_chunks (vector search filters company_id
#     manually — the pipeline processes all companies).
#   - Admin-listing tables with a MANUAL company filter (admin_listing_company_filter),
#     deliberately NOT owned mixins so their other consumers (portal / public /
#     workflow / worker / global audit listener) keep working under any scope —
#     only the staff listing is scoped: forms, import_logs, audit_logs.
_COMPANY_ID_ALLOWLIST = {
    "user_companies",
    "respond_contact_companies",
    "import_jobs",
    "embedding_documents",
    "embedding_chunks",
    "forms",
    "import_logs",
    "audit_logs",
}


def test_every_company_id_table_is_registered():
    offenders = []
    owned = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        table = mapper.local_table.name
        has_company_id = "company_id" in mapper.local_table.columns
        is_owned = isinstance(cls, type) and issubclass(cls, CompanyScopedMixin)
        if is_owned:
            owned.append(table)
        if has_company_id and not is_owned and table not in _COMPANY_ID_ALLOWLIST:
            offenders.append(table)
    assert not offenders, (
        f"Tables have a company_id column but are not CompanyScopedMixin subclasses "
        f"(add the mixin or allowlist them): {offenders}"
    )
    # Foundation slice ships exactly 34 owned tables (PLAN §4.1).
    assert len(owned) == 34, f"expected 34 owned tables, found {len(owned)}: {sorted(owned)}"


# --- AC-D4 system write rejected (UNSET/empty only) ---------------------------
# NOTE: ``None`` is NOT in this list — a None-scope (system / all-companies, the
# n8n no-contact backward-compat path) owned-write now stamps the incumbent
# company (Sorento) rather than rejecting; see the dedicated test below. Only a
# genuinely-ambiguous scope (UNSET = resolver never ran / unresolved contact,
# or an empty frozenset) is rejected.
@pytest.mark.parametrize("scope", [UNSET, frozenset()])
def test_system_write_without_company_is_rejected(scope):
    session = SessionLocal()
    session.begin_nested()
    try:
        with company_scope(session, scope):
            session.add(Brand(brand_code=f"ZZSCOPE-d4-{uuid.uuid4().hex[:8]}", brand_name="d4"))
            with pytest.raises(AppException) as exc:
                session.flush()
        assert exc.value.status_code == 400
    finally:
        session.rollback()


def test_none_scope_owned_write_stamps_incumbent_company():
    """A None-scope (system/all-companies) owned write must NOT reject — it stamps
    the incumbent (Sorento) so n8n no-contact write flows keep working."""
    from app.services.company_scope import DEFAULT_COMPANY_ID

    session = SessionLocal()
    session.begin_nested()
    try:
        with company_scope(session, None):
            b = Brand(brand_code=f"ZZSCOPE-none-{uuid.uuid4().hex[:8]}", brand_name="none")
            session.add(b)
            session.flush()
            assert str(b.company_id) == DEFAULT_COMPANY_ID
    finally:
        session.rollback()
        session.close()


def test_single_company_scope_auto_stamps_on_insert():
    session = SessionLocal()
    session.begin_nested()
    try:
        suffix = uuid.uuid4().hex[:8]
        company = Company(id=str(uuid.uuid4()), name=f"ZZSCOPE stamp {suffix}", code=f"ZS{suffix}")
        session.add(company)
        session.flush()
        with company_scope(session, frozenset({company.id})):
            brand = Brand(brand_code=f"ZZSCOPE-stamp-{suffix}", brand_name="stamp")
            session.add(brand)
            session.flush()
        assert brand.company_id == company.id  # auto-stamped from single-company scope
    finally:
        session.rollback()
        session.close()
