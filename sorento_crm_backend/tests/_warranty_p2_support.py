"""Shared world for the AFTER-SALES-P2 (warranty engine, configuration, job product lines) tests.

Contract (documentation/plans/after-sales/warranty-p2-acceptance-criteria.md, sections E, K, C, J, S):

* models    `app.models.warranty`: `WarrantyProductKind`, `WarrantyKindRule`, `WarrantyPolicy`
            (company scoped), `WarrantyTerm` (columns as unmerged PR #163, minus the assessment
            table); `app.models.service_jobs.ServiceJobProduct` (table `service_job_products`,
            company scoped, `__audit_parent__ = "service_job_id"` so its audit rows have
            root_entity_type "service_jobs" and root_entity_id the job id).
* engine    `app.services.warranty_service`, see tests/test_warranty_p2_engine.py docstring for the
            exact signatures. "Today" is `warranty_service.warranty_today()`, always called through
            the module attribute so the tests can freeze it (also the job-line "future date" check).
* seed      `app.services.warranty_seed.seed_warranty_policy_v15(db, company_id)`.
* routes    under `/api/v1/after-sales`:
              warranty/policies, warranty/kinds, warranty/kind-rules, warranty/terms,
              warranty/policies/{id}/supersede, warranty/kind-rules/test,
              service-jobs/{id}/products (+ /{line_id}).
* wire      lists are `{"data": [...], "pagination": {"total", "page", "limit"}}` with `page`, `limit`,
            `query`, `sort`, `dir` params. Terms: `GET warranty/terms?policy_id=` (a plain list),
            `POST warranty/terms` with `policy_id` in the body, `PATCH|DELETE warranty/terms/{id}`.
* defects   `lookup_options.id` of the set `after_sales_defect_type`.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

import pytest

from ._pg_fixture import unique_code
from ._service_jobs_p1_support import (  # noqa: F401  re-exported for the P2 test files
    ALL_PERMS,
    DISPATCH,
    JOBS,
    VIEW,
    Env,
    api,
    audit_rows,
    env,
    make_job,
)

BASE = "/api/v1/after-sales"
WARRANTY = f"{BASE}/warranty"
POLICIES = f"{WARRANTY}/policies"
KINDS = f"{WARRANTY}/kinds"
RULES = f"{WARRANTY}/kind-rules"
TERMS = f"{WARRANTY}/terms"

TODAY = date(2026, 11, 13)
DEFECT_SET_KEY = "after_sales_defect_type"

# The real shapes seen on dev (codes only): product code, category code.
WC = ("SRTWC6020-SH-UF", "SRT-WC")
CB = ("CB110", "CB-FT")
BA = ("SRT134", "SRT-BA")


def dmy(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def mentions(text: str, value: date) -> bool:
    """A date written dd/mm/yyyy or yyyy-mm-dd."""
    return dmy(value) in text or value.isoformat() in text


@pytest.fixture
def today(monkeypatch):
    """Freeze warranty_today() at 13/11/2026. A missing module/function is left to the test to fail on."""
    try:
        from app.services import warranty_service
    except ImportError:
        return TODAY
    monkeypatch.setattr(warranty_service, "warranty_today", lambda: TODAY, raising=False)
    return TODAY


# ------------------------------------------------------------------ seed helpers


def make_kind(env: Env, code: Optional[str] = None, name: Optional[str] = None, *, active: bool = True, sort_order: int = 0):
    from app.models.warranty import WarrantyProductKind

    code = code or unique_code("zk")[:60]
    row = WarrantyProductKind(
        id=str(uuid.uuid4()), code=code, name=name or f"ZZT {code}", is_active=active, sort_order=sort_order
    )
    env.db.add(row)
    env.db.flush()
    return row


def make_policy(
    env: Env,
    version: Optional[str] = None,
    effective_from: date = date(2000, 1, 1),
    effective_to: Optional[date] = None,
    *,
    company_id: Optional[str] = None,
):
    from app.models.warranty import WarrantyPolicy

    row = WarrantyPolicy(
        id=str(uuid.uuid4()),
        version=(version or unique_code("v"))[:32],
        effective_from=effective_from,
        effective_to=effective_to,
        company_id=company_id or env.company_id,
    )
    env.db.add(row)
    env.db.flush()
    return row


def make_term(
    env: Env,
    policy,
    kind,
    part: str = "Body",
    *,
    months: Optional[int] = None,
    lifetime: bool = False,
    defects=None,
    installation: bool = False,
):
    from app.models.warranty import WarrantyTerm

    row = WarrantyTerm(
        id=str(uuid.uuid4()),
        policy_id=policy.id,
        kind_id=kind.id,
        part_name=part,
        duration_months=months,
        is_lifetime=lifetime,
        covered_defect_type_ids=defects,
        installation_included=installation,
    )
    env.db.add(row)
    env.db.flush()
    return row


def make_rule(env: Env, kind, match_type: str, match_value: str, *, priority: int = 0):
    from app.models.warranty import WarrantyKindRule

    row = WarrantyKindRule(
        id=str(uuid.uuid4()), kind_id=kind.id, match_type=match_type, match_value=match_value, priority=priority
    )
    env.db.add(row)
    env.db.flush()
    return row


def defect(env: Env, label: str) -> str:
    """The id of a defect-type option (`after_sales_defect_type`), created if absent."""
    from app.models.lookup import LookupOption, LookupSet

    lookup_set = env.db.query(LookupSet).filter(LookupSet.set_key == DEFECT_SET_KEY).first()
    if lookup_set is None:
        lookup_set = LookupSet(id=str(uuid.uuid4()), set_key=DEFECT_SET_KEY, name="After-sales defect type")
        env.db.add(lookup_set)
        env.db.flush()
    option = (
        env.db.query(LookupOption)
        .filter(LookupOption.set_id == lookup_set.id, LookupOption.label == label)
        .first()
    )
    if option is None:
        option = LookupOption(
            id=str(uuid.uuid4()), set_id=lookup_set.id, value=f"{label}-{uuid.uuid4().hex[:6]}", label=label, sort_order=0
        )
        env.db.add(option)
        env.db.flush()
    return option.id


def foreign_defect(env: Env) -> str:
    """A real lookup option that is NOT in the defect-type set."""
    from app.models.lookup import LookupOption, LookupSet

    lookup_set = LookupSet(id=str(uuid.uuid4()), set_key=unique_code("zzother")[:70], name="ZZT other set")
    env.db.add(lookup_set)
    env.db.flush()
    option = LookupOption(id=str(uuid.uuid4()), set_id=lookup_set.id, value="other", label="Other", sort_order=0)
    env.db.add(option)
    env.db.flush()
    return option.id


def make_company(env: Env, stem: str = "zzo") -> str:
    from app.models.company import Company

    row = Company(id=str(uuid.uuid4()), name=f"ZZT {stem}", code=unique_code(stem)[:50], is_active=True)
    env.db.add(row)
    env.db.flush()
    return row.id


def make_product(env: Env, code: str, category_code: str, name: Optional[str] = None, *, company_id: Optional[str] = None):
    """A catalogue product (and its category, created once per code)."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    cid = company_id or env.company_id
    category = (
        env.db.query(ProductCategory)
        .filter(ProductCategory.category_code == category_code, ProductCategory.company_id == cid)
        .first()
    )
    if category is None:
        category = ProductCategory(
            id=str(uuid.uuid4()), category_code=category_code, category_name=category_code, company_id=cid
        )
        env.db.add(category)
        env.db.flush()
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=cid)
    env.db.add(uom)
    env.db.flush()
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=name or f"ZZT {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
        company_id=cid,
    )
    env.db.add(row)
    env.db.flush()
    return row


def seed_v15(env: Env, company_id: Optional[str] = None):
    from app.services.warranty_seed import seed_warranty_policy_v15

    seed_warranty_policy_v15(env.db, company_id or env.company_id)
    env.db.flush()


def kind_by_code(env: Env, code: str):
    from app.models.warranty import WarrantyProductKind

    return env.db.query(WarrantyProductKind).filter(WarrantyProductKind.code == code).one()


# ------------------------------------------------------------------ API helpers


def add_line(client, job_id: str, product_id, **body):
    payload = {"product_id": product_id, **body}
    return client.post(f"{JOBS}/{job_id}/products", json=payload)


def line_audit(env: Env, job_id: str) -> list:
    """Audit rows of the job's product lines, as the job's History reads them (root = the job)."""
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    env.db.flush()
    return (
        env.db.query(AuditLog)
        .filter(
            AuditLog.root_entity_type == "service_jobs",
            AuditLog.root_entity_id == job_id,
            AuditLog.entity_type == "service_job_products",
        )
        .order_by(AuditLog.changed_at)
        .all()
    )


def audit_of(env: Env, entity_type: str, entity_id: str) -> list:
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    env.db.flush()
    return (
        env.db.query(AuditLog)
        .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.changed_at)
        .all()
    )
