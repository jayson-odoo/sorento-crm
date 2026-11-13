"""Shared seeds and helpers for the FORMS-LAST-ACTIVITY red tests (all names are fake).

Seeds build their own FK chain (contact, definition, version, user); nothing borrows existing
rows. ``set_stamp`` writes the baseline through a Core UPDATE issued while NO actor is stamped,
so the audit capture treats it as a non-person write and never moves the column itself.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import update, select
from sqlalchemy.orm import Session

import app.main  # noqa: F401  registers every router and model
from app.services.audit_service import register_audit_listeners

register_audit_listeners()

from app.audit_context import AuditActor, actor_scope  # noqa: E402
from app.models.audit import AuditLog  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402
from app.models.new_product_application import NewProductApplication  # noqa: E402
from app.models.price_tag import PriceTagRequest  # noqa: E402
from app.models.procurement import PurchaseRequestHeader, StockInquiry  # noqa: E402
from app.models.sample_request import SampleRequest  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workflow_forms import (  # noqa: E402
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
)

SORENTO = "00000000-0000-0000-0000-000000000001"
MARKER = "ZZT-FLA"
BASE = datetime(2026, 3, 1, 9, 0, 0)


def uid() -> str:
    return str(uuid.uuid4())


def tok() -> str:
    return uuid.uuid4().hex[:8]


def at(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    from datetime import timedelta

    return BASE + timedelta(days=days, hours=hours, minutes=minutes)


def seed_user(db: Session, name: str = "Staffer") -> User:
    row = User(id=uid(), email=f"{MARKER.lower()}-{tok()}@example.test", name=f"{MARKER} {name}", status="ACTIVE")
    db.add(row)
    db.commit()
    return row


def seed_contact(db: Session) -> str:
    from sqlalchemy import text

    cid = uid()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, name, session_vars) "
            "VALUES (:id, :rid, :phone, :name, CAST('{}' AS jsonb))"
        ),
        {
            "id": cid,
            "rid": f"ZZT-{uid()[:8]}",
            "phone": f"+6006{uuid.uuid4().int % 10**7:07d}",
            "name": f"{MARKER} Portal Contact",
        },
    )
    db.commit()
    return cid


def person(db: Session, user: User):
    return actor_scope(AuditActor(actor_type="user", user_id=user.id), db=db)


def non_person(db: Session, actor_type: str):
    return actor_scope(AuditActor(actor_type=actor_type), db=db)


# ----------------------------------------------------------------------------- seeds
def _complaint(db, created_at=None, **kw):
    row = Complaint(id=uid(), complaint_number=f"{MARKER}-C-{tok()}", customer_name=f"{MARKER} Customer",
                    status=kw.pop("status", "new"), created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


def _purchase_request(db, created_at=None, request_type="purchase_request", **kw):
    row = PurchaseRequestHeader(id=uid(), request_number=f"{MARKER}-PR-{tok()}", request_type=request_type,
                                customer_name=f"{MARKER} Customer", status=kw.pop("status", "submitted"),
                                created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


def _price_tag(db, created_at=None, **kw):
    row = PriceTagRequest(id=uid(), contact_id=kw.pop("contact_id", None) or seed_contact(db),
                          doc_number=f"{MARKER}-PT-{tok()}", company_id=SORENTO,
                          created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


def _sample(db, created_at=None, **kw):
    from app.models.status import Status
    from app.services.sample_request_service import ENTITY

    if not db.query(Status).filter(Status.entity_type == ENTITY, Status.scope_id.is_(None)).first():
        db.add(Status(id=uid(), entity_type=ENTITY, key="draft", label="Draft", sort_order=0))
        db.commit()
    row = SampleRequest(id=uid(), request_no=f"ZS{uuid.uuid4().int % 10**7:07d}", company_id=SORENTO,
                        customer_name=f"{MARKER} Customer", created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


def _npa(db, created_at=None, **kw):
    row = NewProductApplication(id=uid(), application_no=f"ZN{uuid.uuid4().int % 10**7:07d}", company_id=SORENTO,
                                customer_name=f"{MARKER} Customer", status=kw.pop("status", "submitted"),
                                created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


def _inquiry(db, created_at=None, **kw):
    row = StockInquiry(id=uid(), inquiry_number=f"{MARKER}-SI-{tok()}", salesperson=f"{MARKER} salesperson",
                       product_code=f"{MARKER}-P", status=kw.pop("status", "new"),
                       created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


def _workflow(db, created_at=None, **kw):
    definition = WorkflowFormDefinition(id=uid(), code=f"zzt-fla-{tok()}", name=f"{MARKER} Definition")
    db.add(definition)
    db.flush()
    version = WorkflowFormVersion(id=uid(), definition_id=definition.id, version_number=1, schema={})
    db.add(version)
    db.flush()
    row = WorkflowSubmission(id=uid(), definition_id=definition.id, version_id=version.id,
                             current_state_code=kw.pop("current_state_code", "submitted"),
                             created_at=created_at or at(), **kw)
    db.add(row)
    db.commit()
    return row


@dataclass(frozen=True)
class Form:
    key: str
    model: Any
    seed: Callable[..., Any]
    audit_entity_type: str
    link_entity_type: str | None
    edit: tuple[str, Any]  # a plain header field a person can change
    url: str | None  # list endpoint (None: service-level only)
    rows_key: str = "data"
    comment_kind: str | None = None


FORMS = [
    Form("complaint", Complaint, _complaint, "complaint", "complaint", ("customer_name", "ZZT-FLA Edited"),
         "/api/v1/complaints-management/complaints/", comment_kind="complaint"),
    Form("purchase_request", PurchaseRequestHeader, _purchase_request, "purchase_request", "purchase_request",
         ("customer_name", "ZZT-FLA Edited"), "/api/v1/procurement/purchase-requests/",
         comment_kind="purchase_request"),
    Form("price_tag_request", PriceTagRequest, _price_tag, "price_tag_requests", "price_tag_request",
         ("status", "in_progress"), "/api/v1/dealer-kit/price-tag-requests"),
    Form("sample_request", SampleRequest, _sample, "project_sample_requests", "sample_request",
         ("ship_to_name", "ZZT-FLA Edited"), "/api/v1/project-sales/sample-requests", comment_kind="sample_request"),
    Form("new_product_application", NewProductApplication, _npa, "new_product_application",
         "new_product_application", ("customer_name", "ZZT-FLA Edited"),
         "/api/v1/procurement/new-product-applications", rows_key="items"),
    Form("stock_inquiry", StockInquiry, _inquiry, "stock_inquiry", "stock_inquiry", ("remark", "ZZT-FLA Edited"),
         "/api/v1/procurement/stock-inquiries/", comment_kind="stock_inquiry"),
    Form("workflow_submission", WorkflowSubmission, _workflow, "workflow_submissions", None,
         ("current_state_code", "approved"), None),
]
BY_KEY = {f.key: f for f in FORMS}
IDS = [f.key for f in FORMS]


# ----------------------------------------------------------------------------- stamp helpers
def set_stamp(db: Session, row: Any, value: datetime | None) -> None:
    """Baseline: write ``last_activity_at`` with no actor stamped (a non-person write)."""
    table = type(row).__table__
    db.execute(update(table).where(table.c.id == row.id).values(last_activity_at=value)
               .execution_options(synchronize_session=False))
    db.commit()


def stamp(db: Session, row: Any) -> datetime | None:
    db.expire_all()
    table = type(row).__table__
    return db.execute(select(table.c.last_activity_at).where(table.c.id == row.id)).scalar_one()


def newest_audit(db: Session, row: Any, *, actor_types=("user", "contact", "public_link")) -> AuditLog | None:
    from sqlalchemy import or_

    rid = str(row.id)
    return (
        db.query(AuditLog)
        .filter(or_(AuditLog.entity_id == rid, AuditLog.root_entity_id == rid), AuditLog.actor_type.in_(actor_types))
        .order_by(AuditLog.changed_at.desc())
        .first()
    )


OLD = datetime(2020, 1, 1, 0, 0, 0)
