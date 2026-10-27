"""SALES-UNIFIED S1: schema and ingest (AC-1 to AC-4).

UAC `documentation/plans/sales/sales-unified-27oct-acceptance-criteria.md`, contract sections 1
and 6. Postgres only (a blank scratch schema), every row seeded here.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import MarketSegment
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.order import Customer
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.master_ingest_service import IngestOutcome, MasterIngestService
from tests._pg_fixture import blank_session, unique_code
from tests.test_top_selling_report import _seed_superadmin


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


@pytest.fixture
def svc(db):
    return MasterIngestService(db, integration_id=None, company_id=DEFAULT_COMPANY_ID)


def _push(svc, code, **extra):
    record = {"source_ref": f"DK-{code}", "code": code, "name": f"Name {code}", **extra}
    result = svc.ingest("customers", [record])
    return result.records[0]


def _row(db, code) -> Customer:
    return db.query(Customer).filter(Customer.customer_code == code).one()


def test_ac_1_a_raw_debtor_type_is_stored_upper_and_trimmed_and_an_unknown_value_still_warns(db, svc):
    code = unique_code("ZZTC")
    rec = _push(svc, code, market_segment_code=" bravat ")
    assert rec.outcome is IngestOutcome.CREATED, rec.errors
    assert "segment_unknown" in rec.warnings
    row = _row(db, code)
    assert row.autocount_debtor_type == "BRAVAT"
    assert row.market_segment_code is None


def test_ac_1_a_matching_market_segment_also_stores_the_debtor_type(db, svc):
    seg = unique_code("ZZTSEG")[:40].upper()
    db.add(MarketSegment(id=str(uuid.uuid4()), code=seg, name=seg, is_active=True))
    db.flush()
    code = unique_code("ZZTC")
    rec = _push(svc, code, market_segment_code=f"  {seg.lower()} ")
    assert rec.outcome is IngestOutcome.CREATED, rec.errors
    assert "segment_unknown" not in rec.warnings
    row = _row(db, code)
    assert row.market_segment_code == seg
    assert row.autocount_debtor_type == seg


def test_ac_1_a_later_push_updates_the_stored_debtor_type(db, svc):
    code = unique_code("ZZTC")
    _push(svc, code, market_segment_code="acct i")
    rec = _push(svc, code, market_segment_code="acct ii")
    assert rec.outcome is IngestOutcome.UPDATED, rec.errors
    assert _row(db, code).autocount_debtor_type == "ACCT II"


def test_ac_2_a_push_without_market_segment_code_leaves_the_debtor_type_untouched(db, svc):
    code = unique_code("ZZTC")
    _push(svc, code, market_segment_code="bravat")
    rec = _push(svc, code, region="NORTH")  # same customer, no market_segment_code key
    assert rec.outcome is IngestOutcome.UPDATED, rec.errors
    db.expire_all()
    assert _row(db, code).autocount_debtor_type == "BRAVAT"


def test_ac_2_a_push_that_creates_a_customer_without_the_key_stores_null(db, svc):
    code = unique_code("ZZTC")
    _push(svc, code)
    assert _row(db, code).autocount_debtor_type is None


def test_ac_3_the_crm_debtor_type_is_never_written_by_the_push(db, svc):
    code = unique_code("ZZTC")
    created = _push(svc, code, market_segment_code="bravat")
    assert created.outcome is IngestOutcome.CREATED, created.errors
    row = _row(db, code)
    assert row.debtor_type != "BRAVAT"
    row.debtor_type = "project_cash"
    db.flush()
    _push(svc, code, market_segment_code="other")
    db.expire_all()
    row = _row(db, code)
    assert row.debtor_type == "project_cash"
    assert row.autocount_debtor_type == "OTHER"


# ------------------------------------------------------------------------------ AC-4


def test_ac_4_sales_agent_source_defaults_to_document(db):
    company = Company(id=str(uuid.uuid4()), name="Zzt Co", code=unique_code("ZC")[:20])
    db.add(company)
    db.flush()
    db.refresh(company)
    assert company.sales_agent_source == "document"


def test_ac_4_the_database_rejects_any_other_value(db):
    company = Company(id=str(uuid.uuid4()), name="Zzt Co", code=unique_code("ZC")[:20])
    db.add(company)
    db.flush()
    for bad in ("both", "", "Document"):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text("UPDATE companies SET sales_agent_source = :v WHERE id = :i"),
                           {"v": bad, "i": company.id})
    for good in ("customer", "document"):
        db.execute(text("UPDATE companies SET sales_agent_source = :v WHERE id = :i"),
                   {"v": good, "i": company.id})


@contextmanager
def _admin_client(db):
    principal = _seed_superadmin(db)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _form(company, **over):
    body = {"name": company.name, "code": company.code, "is_active": True, "so_feed_live": True}
    body.update(over)
    return body


def test_ac_4_the_companies_update_route_saves_it_and_absent_leaves_it_unchanged(db):
    company = Company(id=str(uuid.uuid4()), name="Zzt Co", code=unique_code("ZC")[:20])
    db.add(company)
    db.flush()
    url = f"/api/v1/system/companies/{company.id}"
    with _admin_client(db) as client:
        saved = client.put(url, json=_form(company, sales_agent_source="customer"))
        assert saved.status_code == 200, saved.text
        assert saved.json()["sales_agent_source"] == "customer"
        db.expire_all()
        assert db.get(Company, company.id).sales_agent_source == "customer"

        kept = client.put(url, json=_form(company, name="Zzt Co Renamed"))
        assert kept.status_code == 200, kept.text
        assert kept.json()["sales_agent_source"] == "customer"

        bad = client.put(url, json=_form(company, sales_agent_source="both"))
        assert bad.status_code == 422, bad.text
        db.expire_all()
        assert db.get(Company, company.id).sales_agent_source == "customer"
