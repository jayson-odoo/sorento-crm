"""Company-scoped filtering of the four staff admin listings.

The tables backing these listings (``import_jobs``, ``import_logs``, ``forms``,
``audit_logs``) each carry a ``company_id`` but are DELIBERATELY NOT
``CompanyScopedMixin`` owned tables (their portal / public / workflow / worker /
audit-listener consumers must stay unscoped). Only the staff LISTING splices a
manual predicate via ``admin_listing_company_filter``. This file pins that
predicate end-to-end through each ``list_*`` entry point:

  * a single-company (Mocha) scope -> only Mocha rows + legacy-NULL rows
  * a single-company (Sorento) scope -> only Sorento rows + legacy-NULL rows
  * ``None`` (all-companies / system) -> every row

Runs against the local Postgres dev DB (a prod-copy) inside a nested transaction
that is ALWAYS rolled back. Every seeded row carries a ``ZZADMIN``/``zzadmin``
marker and each listing is queried through its own marker filter so the assertions
never see real data.
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.database import SessionLocal
from app.models.audit import AuditLog
from app.models.company import Company
from app.models.forms import Form
from app.models.import_log import ImportLog
from app.models.job import ImportJob
from app.services.audit_service import list_audit_logs
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.forms_service import FormService
from app.services.import_log_service import ImportLogService
from app.services.job_service import JobService

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


@pytest.fixture()
def db():
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def data(db):
    """Two throwaway companies (Mocha, Sorento stand-ins) plus one Mocha / one
    Sorento / one company-less (NULL) row in each of the four admin tables."""
    suffix = uuid.uuid4().hex[:8]
    mocha = Company(id=str(uuid.uuid4()), name=f"ZZADMIN Mocha {suffix}", code=f"ZM{suffix}")
    sorento = Company(id=str(uuid.uuid4()), name=f"ZZADMIN Sorento {suffix}", code=f"ZS{suffix}")
    db.add_all([mocha, sorento])
    db.flush()
    m, s = mocha.id, sorento.id

    marker = f"zzadmin-{suffix}"
    ids: dict[str, dict[str, str]] = {t: {} for t in ("job", "log", "form", "audit")}

    for tag, company_id in (("mocha", m), ("sorento", s), ("null", None)):
        job = ImportJob(
            id=uuid.uuid4(),
            job_id=f"{marker}-{tag}",
            job_type=marker,
            user_id=marker,
            status="finished",
            company_id=company_id,
        )
        log = ImportLog(
            import_session_id=f"{marker}-{tag}",
            entity_type=marker,
            entity_table="zzadmin",
            import_type="create",
            company_id=company_id,
        )
        form = Form(
            code=f"{marker}-{tag}",
            name=f"ZZADMIN form {marker} {tag}",
            company_id=company_id,
        )
        audit = AuditLog(
            entity_type="zzadmin",
            entity_id=str(uuid.uuid4()),
            action="UPDATE",
            trace_id=marker,
            company_id=company_id,
        )
        db.add_all([job, log, form, audit])
        db.flush()
        ids["job"][tag] = str(job.id)
        ids["log"][tag] = str(log.id)
        ids["form"][tag] = str(form.id)
        ids["audit"][tag] = str(audit.id)

    return {"m": m, "s": s, "marker": marker, "ids": ids}


# --- collectors: return the seeded ids the listing surfaced -------------------
def _job_ids(db, marker):
    jobs = JobService(db).list_jobs(job_type=marker, limit=100)
    return {str(j.id) for j in jobs}


def _log_ids(db, marker):
    resp = ImportLogService(db).list_import_logs(page=1, limit=100, entity_type=marker)
    return {str(r.id) for r in resp.data}


def _form_ids(db, marker):
    result = FormService(db).list_forms(page=1, limit=100, query=marker)
    return {str(f.id) for f in result["data"]}


def _audit_ids(db, marker):
    items, _total = list_audit_logs(db, trace_id=marker, limit=100)
    return {str(i.id) for i in items}


_COLLECTORS = {
    "job": _job_ids,
    "log": _log_ids,
    "form": _form_ids,
    "audit": _audit_ids,
}


@pytest.mark.parametrize("table", list(_COLLECTORS))
def test_single_company_scope_shows_that_company_plus_null(db, data, table):
    collect = _COLLECTORS[table]
    seeded = data["ids"][table]
    marker = data["marker"]

    # Sorento scope -> Sorento + NULL, never Mocha.
    with company_scope(db, frozenset({data["s"]})):
        got = collect(db, marker)
    assert got == {seeded["sorento"], seeded["null"]}, f"{table} leaked under Sorento scope: {got}"

    # Mocha scope -> Mocha + NULL, never Sorento.
    with company_scope(db, frozenset({data["m"]})):
        got = collect(db, marker)
    assert got == {seeded["mocha"], seeded["null"]}, f"{table} leaked under Mocha scope: {got}"


@pytest.mark.parametrize("table", list(_COLLECTORS))
def test_none_scope_shows_all_companies(db, data, table):
    collect = _COLLECTORS[table]
    seeded = data["ids"][table]
    with company_scope(db, None):
        got = collect(db, data["marker"])
    assert got == {seeded["mocha"], seeded["sorento"], seeded["null"]}
