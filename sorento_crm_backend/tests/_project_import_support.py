"""Shared seeding for the project import tests (lane PROJECT-MIGRATION-TOOL, slice 1).

Contract: `documentation/plans/project-sales/PLAN-project-import-12nov.md` ("Backend
contract") and the UAC `project-import-12nov-acceptance-criteria.md` (AC-PI-01..51).

Postgres only, through `tests/_pg_fixture.py::blank_session` (a blank scratch schema, every
write rolled back). Every FK target is seeded here; nothing is borrowed from an existing row,
because CI's database is empty. Fake names only.

The source file is kept on the run through the normal import storage path
(`import_jobs.source_file_key`); storage is replaced by an in-memory backend so a preview can
read the bytes back without a bucket.
"""
from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

import openpyxl
import pytest
import sqlalchemy as sa

from tests.fixtures.project_import.build_so_summary import (
    FIELDS,
    HEADER_BY_FIELD,
    HEADERS,
    fold,
)

from ._pg_fixture import blank_session

MARKER = "ZZT-PIM"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

__all__ = [
    "FIELDS", "HEADERS", "HEADER_BY_FIELD", "MARKER", "XLSX", "fold", "make_book", "row",
    "World", "seed_customer", "seed_core_so", "seed_party", "seed_user", "seed_project",
    "seed_company", "new_run", "snapshot", "invoiced_total", "api_client", "grant",
    "memory_storage", "world",
]


def _uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- workbooks


def row(ps: str, **cells) -> dict:
    """One register row keyed by contract field. Defaults give a complete, clean row."""
    base = {
        "ps_number": ps,
        "salesperson": "ALVIN",
        "customer_service": "KATE",
        "customer": "CUSTOMER 001 SDN BHD",
        "project_name": "PROJECT 001 SAMPLE NAME",
        "developer": None,
        "po_number": f"PO-{ps[-4:]}",
        "po_value": 1000,
        "po_date": datetime(2026, 1, 5),
        "amended_date": None,
        "schedule": "YES",
        "delivery": None,
        "outstanding": None,
        "so_number": None,
        "remarks": None,
    }
    base.update(cells)
    return base


def make_book(
    sheets: dict[str, list[dict]],
    *,
    field_order: Optional[list[str]] = None,
    drop_fields: Iterable[str] = (),
    extra_sheets: Optional[dict[str, list[list]]] = None,
) -> bytes:
    """An in-memory register workbook: one header row (verbatim headings) + the rows.

    `field_order` reorders the columns (AC-PI-01); `drop_fields` leaves a heading out
    (AC-PI-02); `extra_sheets` adds raw sheets (a SUMMARY-like sheet, junk).
    """
    order = [f for f in (field_order or FIELDS) if f not in set(drop_fields)]
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for col, f in enumerate(order, start=1):
            ws.cell(row=1, column=col, value=HEADER_BY_FIELD[f])
        for r, values in enumerate(rows, start=2):
            for col, f in enumerate(order, start=1):
                value = values.get(f)
                if value is not None:
                    ws.cell(row=r, column=col, value=value)
    for name, raw_rows in (extra_sheets or {}).items():
        ws = wb.create_sheet(title=name)
        for raw in raw_rows:
            ws.append(raw)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- storage


class _MemoryBackend:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def upload_file(self, data, key, content_type=None, *args, **kwargs):
        self.files[key] = data if isinstance(data, bytes) else data.read()
        return key

    def upload_fileobj(self, fileobj, key, *args, **kwargs):
        self.files[key] = fileobj.read()
        return key

    def download_file(self, key):
        return self.files[key]

    def file_exists(self, key):
        return key in self.files

    def delete_file(self, key):
        return self.files.pop(key, None) is not None

    def copy_file(self, old_key, new_key):
        self.files[new_key] = self.files[old_key]

    def get_signed_url(self, key, expires_in=3600):
        return f"https://memory.invalid/{key}"


@pytest.fixture
def memory_storage(monkeypatch):
    from app.services import storage_router

    backend = _MemoryBackend()
    monkeypatch.setattr(storage_router, "_backends", {"s3": backend, "r2": backend})
    return backend


# --------------------------------------------------------------------------- seeding


def seed_user(db, name: str, company_id: Optional[str] = None, *, active: bool = True) -> str:
    """A user; ACTIVE by default, with a grant in `company_id` when one is given (a person
    target must be an active user granted in the run's company, SEC-S2)."""
    from app.models.company import UserCompany
    from app.models.user import User

    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name,
                status="ACTIVE" if active else "INACTIVE"))
    db.flush()
    if company_id:
        db.add(UserCompany(user_id=user_id, company_id=company_id))
        db.flush()
    return user_id


def seed_company(db, label: str = "Other") -> str:
    from app.models.company import Company

    company_id = _uid()
    db.add(Company(id=company_id, name=f"{MARKER} {label}", code=f"Z{uuid.uuid4().hex[:7]}".upper(),
                   is_active=True))
    db.flush()
    return company_id


def seed_customer(db, company_id: str, name: str, *, group_id: Optional[str] = None):
    from app.models.order import Customer

    row_ = Customer(
        id=_uid(),
        customer_code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper(),
        customer_name=name,
        company_id=company_id,
        customer_group_id=group_id,
    )
    db.add(row_)
    db.flush()
    return row_


def seed_group(db, company_id: str, name: str) -> str:
    from app.models.order import CustomerGroup

    group = CustomerGroup(id=_uid(), name=name, company_id=company_id)
    db.add(group)
    db.flush()
    return group.id


def seed_core_so(db, company_id: str, so_number: str, customer, *, demand_class="project"):
    """A synced AutoCount sales order (core `sales_orders`), project class."""
    from app.models.order import SalesOrder

    so = SalesOrder(
        id=_uid(),
        so_number=so_number,
        status="open",
        demand_class=demand_class,
        source_system="autocount",
        order_date=datetime(2026, 1, 6).date(),
        customer_id=customer.id if customer is not None else None,
        company_id=company_id,
    )
    db.add(so)
    db.flush()
    return so


def seed_party(db, company_id: str, name: str, *, party_type="developer", customer_id=None):
    from app.models.projects import ProjectParty

    party = ProjectParty(
        id=_uid(), company_id=company_id, party_type=party_type, name=name,
        customer_id=customer_id,
    )
    db.add(party)
    db.flush()
    return party


def seed_project(db, company_id: str, owner: str, title: str, *, developer_party_id=None):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=developer_party_id,
        title=title,
        skip_clash_check=True,
    )


@dataclass
class World:
    db: object
    company_id: str
    admin_id: str
    storage: object
    extra: dict = field(default_factory=dict)


@pytest.fixture
def world(memory_storage):
    """Company SRT with the project funnel + numbering seeded, one importing user."""
    from app.models.base import company_scope
    from app.services import project_seed_service
    from app.services.audit_service import register_audit_listeners

    # Production registers the audit listeners at startup (app.main, worker.py). A test file
    # run alone may never import app.main, so register them here; the call is idempotent.
    register_audit_listeners()
    with blank_session() as db:
        company_id = str(
            db.execute(sa.text("select id from companies where code = 'SRT'")).scalar()
        )
        with company_scope(db, frozenset({company_id})):
            project_seed_service.run(db, company_id=company_id)
            admin_id = seed_user(db, f"{MARKER} Importer", company_id)
            db.commit()
            yield World(db=db, company_id=company_id, admin_id=admin_id, storage=memory_storage)


def sheet_names(content: bytes) -> list[str]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    try:
        return [n for n in wb.sheetnames if n.strip() != "SUMMARY JAN-JUN"]
    finally:
        wb.close()


def new_run(w: World, content: bytes, *, filename="SO SUMMARY 2026.xlsx", sheets=None,
            columns=None, user_id=None):
    """create_run + save_columns with the file's own headings and every register sheet."""
    from app.services.project_import import service

    run = service.create_run(
        w.db, company_id=w.company_id, user_id=user_id or w.admin_id, filename=filename,
        content=content,
    )
    service.save_columns(
        w.db, run,
        sheets=sheets if sheets is not None else sheet_names(content),
        columns=dict(columns if columns is not None else HEADER_BY_FIELD),
        user_id=user_id or w.admin_id,
    )
    return run


# --------------------------------------------------------------------------- counting


_COUNTED = {
    "projects": "projects.projects",
    "sales_profiles": "projects.sales_profile",
    "purchase_orders": "projects.purchase_orders",
    "parties": "projects.parties",
    "project_sales_orders": "projects.sales_orders",
    "project_tasks": "projects.tasks",
    "notifications": "notifications",
    "notification_deliveries": "notification_deliveries",
    "email_outbox": "email_outbox",
}


def snapshot(db) -> dict:
    """Row counts of every table an import could write to (scratch schema: all ours)."""
    from app.models.audit import AuditLog
    from app.models.integration import IntegrationLog
    from app.models.notification import Notification, NotificationDelivery
    from app.models.email_outbox import EmailOutbox  # noqa: F401  table registered
    from app.models.projects import (
        Project,
        ProjectParty,
        ProjectPurchaseOrder,
        ProjectSalesProfile,
        ProjectTask,
    )
    from app.models.project_so import ProjectSalesOrder

    db.flush()
    out = {
        "projects": db.query(Project).count(),
        "sales_profiles": db.query(ProjectSalesProfile).count(),
        "purchase_orders": db.query(ProjectPurchaseOrder).count(),
        "parties": db.query(ProjectParty).count(),
        "project_sales_orders": db.query(ProjectSalesOrder).count(),
        "project_tasks": db.query(ProjectTask).count(),
        "notifications": db.query(Notification).count(),
        "notification_deliveries": db.query(NotificationDelivery).count(),
        "email_outbox": db.execute(sa.text("select count(*) from email_outbox")).scalar(),
        "integration_outbound": db.query(IntegrationLog)
        .filter(IntegrationLog.direction == "outbound")
        .count(),
        # The run's own bookkeeping (import_jobs / import_job_rows, and the run's own History
        # entries, entity type project_import_run, round 3) is allowed to change.
        "audit_rows": db.query(AuditLog)
        .filter(~AuditLog.entity_type.in_(["import_jobs", "import_job_rows", "import_job",
                                           "import_job_row", "project_import_run"]))
        .count(),
    }
    return out


def invoiced_total(db, company_id: str) -> Decimal:
    """The shared invoiced sales total (`app/services/sales/invoiced_sales.py`)."""
    from app.models.finance import BillingDocument
    from app.services.sales.invoiced_sales import posted, signed_amount

    value = (
        db.query(sa.func.coalesce(sa.func.sum(signed_amount()), 0))
        .select_from(BillingDocument)
        .filter(posted())
        .scalar()
    )
    return Decimal(str(value or 0))


# --------------------------------------------------------------------------- api


def grant(monkeypatch, slugs: set[str]) -> None:
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission",
        lambda self, uid, slug: slug in slugs,
    )
    monkeypatch.setattr(
        UserPermissionService, "get_user_permission_slugs", lambda self, uid: sorted(slugs)
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"user"},
                        raising=False)


@pytest.fixture
def api_client(monkeypatch):
    """`make(db, user_id, company_id, slugs)` -> TestClient on the real app over `db`."""
    from fastapi.testclient import TestClient

    from app import database
    from app import dependencies
    from app.main import app
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    def make(db, user_id: str, company_id: str, slugs: set[str]):
        actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user",
                 "name": f"{MARKER} user"}

        def _db():
            yield db

        app.dependency_overrides[database.get_db] = _db
        app.dependency_overrides[dependencies.get_db] = _db
        app.dependency_overrides[dependencies.get_current_user] = lambda: dict(actor)
        app.dependency_overrides[dependencies.get_current_user_or_api_key] = lambda: dict(actor)

        def _scope():
            scope = frozenset({company_id})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _scope
        grant(monkeypatch, slugs)
        return TestClient(app, raise_server_exceptions=False)

    yield make
    from app.main import app as _app

    _app.dependency_overrides.clear()
