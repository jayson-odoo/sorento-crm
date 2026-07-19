"""Regression coverage for the portal Sales-type alignment deltas.

Two behaviours added while aligning the portal with the system form view:

PORTAL-1  /public/portal/lookups/sets/{set_key} returns the binding's
          default_value so a NEW portal form pre-selects the same option the
          system LookupBoundField would (e.g. procurement_sales_type -> project).
PORTAL-2  sales_type is an editable portal field for PR/SF (kind != complaint /
          stock_inquiry), and is NOT leaked into the complaint / stock_inquiry
          editable sets.

The endpoint handler is a plain function, so we call it directly with a seeded
in-memory session instead of standing up the portal-token HTTP dependency.
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# MUST be first app import — resolves circular-import in app.modules.runtime.guards
from app.main import app  # noqa: F401,E402
from app.api.v1.public.portal import lookup_set_options
from app.database import Base
from app.models.lookup import LookupBinding, LookupOption, LookupSet
from app.services.portal_service import PortalService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[LookupSet.__table__, LookupOption.__table__, LookupBinding.__table__],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_sales_type(db, *, default_value: str | None) -> None:
    set_id = str(uuid.uuid4())
    db.add(LookupSet(id=set_id, set_key="procurement_sales_type", name="Sales type"))
    db.add(LookupOption(set_id=set_id, value="project", label="Project", sort_order=0))
    db.add(LookupOption(set_id=set_id, value="cash_sales", label="Cash sales", sort_order=1))
    db.add(
        LookupBinding(
            set_id=set_id,
            table_name="purchase_requests",
            column_name="sales_type",
            default_value=default_value,
        )
    )
    db.commit()


# ---------- PORTAL-1: endpoint surfaces the binding default ----------

def test_lookup_set_returns_binding_default(db):
    _seed_sales_type(db, default_value="project")
    res = lookup_set_options(set_key="procurement_sales_type", token=object(), db=db)
    assert [o.value for o in res.options] == ["project", "cash_sales"]
    assert res.default_value == "project"


def test_lookup_set_default_none_when_binding_unset(db):
    _seed_sales_type(db, default_value=None)
    res = lookup_set_options(set_key="procurement_sales_type", token=object(), db=db)
    assert res.default_value is None
    assert len(res.options) == 2


def test_lookup_set_non_whitelisted_rejected(db):
    with pytest.raises(HTTPException) as ei:
        lookup_set_options(set_key="secret_internal_set", token=object(), db=db)
    assert ei.value.status_code == 403


# ---------- PORTAL-2: sales_type editable only for PR/SF ----------

def test_sales_type_editable_for_pr(db):
    fields = PortalService(db)._editable_fields("purchase_request")
    assert "sales_type" in fields


def test_sales_type_editable_for_sponsorship(db):
    # SF shares the PR (else-branch) editable set.
    fields = PortalService(db)._editable_fields("sponsorship_form")
    assert "sales_type" in fields


def test_sales_type_not_editable_for_complaint_or_stock_inquiry(db):
    svc = PortalService(db)
    assert "sales_type" not in svc._editable_fields("complaint")
    assert "sales_type" not in svc._editable_fields("stock_inquiry")
