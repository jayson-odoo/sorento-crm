"""Creating an SLA policy must stamp, and check uniqueness within, the active company.

`sla_policies.company_id` is NOT NULL and the code is unique per `(code, company_id)`,
but `SLAPolicy` is deliberately not a `CompanyScopedMixin` (the auto-filter reaches
every policy load in the app, including readers holding a policy id with no company
context). Nothing else filled the gap on the write path, so `create_policy`:

  * inserted `company_id = NULL` -> psycopg2 NotNullViolation, the raw SQL leaked to
    the user as a toast; and
  * checked the code globally, so creating "PURCHASING" while switched to Mocha was
    rejected with "SLA policy code already exists in this company" when the only row
    with that code belonged to Sorento.

Both reproduced in the browser on the Create SLA Policy page under Mocha.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.company import Company
from app.models.sla import SLAPolicy
from app.schemas.sla import SLAPolicyCreate
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.error_handler import AppException
from app.services.sla_service import SLAPolicyService

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

MARKER = "ZZTPOL"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def companies(db: Session):
    """Two throwaway companies, cleaned up by id afterwards (the dev database is a
    copy of production, and a stray company row shows up in the switcher)."""
    suffix = uuid.uuid4().hex[:8]
    a = Company(id=str(uuid.uuid4()), name=f"{MARKER} A {suffix}", code=f"ZPA{suffix}")
    b = Company(id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZPB{suffix}")
    db.add_all([a, b])
    db.commit()
    try:
        yield {"a": a.id, "b": b.id, "code": f"{MARKER}-{suffix}"}
    finally:
        db.rollback()
        db.execute(
            sa_text("DELETE FROM sla_policies WHERE company_id IN (:a, :b)"),
            {"a": a.id, "b": b.id},
        )
        db.execute(
            sa_text("DELETE FROM companies WHERE id IN (:a, :b)"), {"a": a.id, "b": b.id}
        )
        db.commit()


def _create(db: Session, code: str) -> SLAPolicy:
    return SLAPolicyService(db).create_policy(
        SLAPolicyCreate(code=code, name=f"{MARKER} policy", is_active=True)
    )


def test_create_stamps_the_active_company(db: Session, companies):
    with company_scope(db, frozenset({companies["a"]})):
        policy = _create(db, companies["code"])
    assert str(policy.company_id) == str(companies["a"])


def test_same_code_allowed_in_a_second_company(db: Session, companies):
    """The whole point of per-company policy codes: Mocha gets its own PURCHASING."""
    with company_scope(db, frozenset({companies["a"]})):
        _create(db, companies["code"])
    with company_scope(db, frozenset({companies["b"]})):
        second = _create(db, companies["code"])
    assert str(second.company_id) == str(companies["b"])

    rows = (
        db.query(SLAPolicy.company_id)
        .filter(SLAPolicy.code == companies["code"])
        .all()
    )
    assert {str(r[0]) for r in rows} == {str(companies["a"]), str(companies["b"])}


def test_duplicate_code_within_one_company_still_conflicts(db: Session, companies):
    with company_scope(db, frozenset({companies["a"]})):
        _create(db, companies["code"])
        with pytest.raises(AppException) as exc:
            _create(db, companies["code"])
    assert exc.value.status_code == 409
