"""Shared sqlite harness for the form-void test suite (not collected by pytest).

Builds an in-memory sqlite session with just the tables the void flow touches,
a TestClient wired to a dynamic actor, and grant-based permission stubbing.
Mirrors the pattern in tests/test_form_handling_lock_routes.py (CLAUDE.md
"sqlite pytest fixtures" gotcha: JSONB->JSON, drop pg-only partial indexes).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB
from sqlalchemy.types import JSON as GenericJSON

from app.database import Base
from app.models.user import User
from app.models.procurement import (
    PurchaseRequestHeader,
    PurchaseRequestLine,
    StockInquiry,
)
from app.models.complaints import Complaint, ComplaintProductLine
from app.models.sla import (
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
    ConversationSLATracking,
    ConversationSLAEventLog,
)
from app.models.access import RespondContact, AccessAgent


_MODELS = [
    User,
    AccessAgent,
    PurchaseRequestHeader,
    PurchaseRequestLine,
    StockInquiry,
    Complaint,
    ComplaintProductLine,
    SLAPolicy,
    SLAPolicyTier,
    FormSLAConfig,
    ConversationSLATracking,
    ConversationSLAEventLog,
    RespondContact,
]

# actor id -> set of granted permission slugs (superadmin bypass emulated by "*")
ACTOR_GRANTS: dict[str, set[str]] = {}


def _sqlite_safe(model) -> None:
    for col in list(model.__table__.columns):
        if isinstance(col.type, (JSONB, PG_ARRAY)):
            col.type = GenericJSON()
            col.server_default = None
    # Drop Postgres-only partial/expression indexes that sqlite can't compile.
    for idx in list(model.__table__.indexes):
        if idx.dialect_options.get("postgresql", {}).get("where") is not None:
            model.__table__.indexes.discard(idx)


def make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for m in _MODELS:
        _sqlite_safe(m)
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _MODELS])
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def new_user(db, *, name="Actor", email=None) -> str:
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=email or f"{uid}@t.com", name=name, status="ACTIVE"))
    db.commit()
    return uid


def new_pr(db, *, request_type="purchase_request", status="approved", approval_status="approved", number="PR-1"):
    pid = str(uuid.uuid4())
    db.add(PurchaseRequestHeader(
        id=pid, request_type=request_type, request_number=number,
        status=status, approval_status=approval_status, source="manual",
    ))
    db.commit()
    return pid


def new_complaint(db, *, status="approved", number="CMP-1"):
    cid = str(uuid.uuid4())
    db.add(Complaint(id=cid, complaint_number=number, status=status))
    db.commit()
    return cid


def new_stock_inquiry(db, *, status="pending_purchasing", number="SI-1"):
    sid = str(uuid.uuid4())
    db.add(StockInquiry(id=sid, inquiry_number=number, status=status))
    db.commit()
    return sid


def new_policy(db):
    pid = str(uuid.uuid4())
    db.add(SLAPolicy(id=pid, code=f"P{pid[:6]}", name="Policy"))
    db.add(SLAPolicyTier(id=str(uuid.uuid4()), policy_id=pid, tier_level=1,
                         tier_name="T1", response_hours=4, resolution_hours=24))
    db.commit()
    return pid


def new_config(db, *, source_entity_type, resolve_event, policy_id, stage="cs"):
    cid = str(uuid.uuid4())
    db.add(FormSLAConfig(
        id=cid, source_entity_type=source_entity_type, stage_code=stage,
        policy_id=policy_id, agent_code=source_entity_type, team_set_code="cs",
        start_event="submitted", respond_event=None, resolve_event=resolve_event,
        is_active=True,
    ))
    db.commit()
    return cid


def new_tracker(db, *, source_entity_type, source_entity_id, policy_id,
                assigned_to_id=None, handled_by_id=None, is_resolved=False):
    now = datetime.utcnow()
    tid = str(uuid.uuid4())
    db.add(ConversationSLATracking(
        id=tid, policy_id=policy_id, current_tier=1,
        initiated_at=now - timedelta(hours=2),
        current_tier_started_at=now - timedelta(hours=1),
        due_at=now + timedelta(hours=4), due_at_resolution=now + timedelta(hours=20),
        is_resolved=is_resolved, source_entity_type=source_entity_type,
        source_entity_id=str(source_entity_id), team_set_code="cs",
        assigned_to_id=assigned_to_id, handled_by_id=handled_by_id,
        handled_at=now if handled_by_id else None,
    ))
    db.commit()
    return tid


def make_client(db, actor_holder: dict):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor_holder)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor_holder)
    return TestClient(app)


def patch_permissions(monkeypatch):
    """check_user_has_permission consults ACTOR_GRANTS; '*' means superadmin."""
    from app.services.user_service import UserPermissionService

    def _check(self, uid, slug):
        grants = ACTOR_GRANTS.get(str(uid), set())
        return "*" in grants or slug in grants

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _check)


def patch_serializers(monkeypatch):
    """Stub view-url builders + attachment listing so the detail serializers used
    by the complaint / stock-inquiry void responses don't hit view_tokens (isolated
    session) or entity_attachment_links (table not in the fixture)."""
    from app.services.procurement_service import StockInquiryService
    from app.services.complaints_service import ComplaintService
    from app.services.entity_attachment_service import EntityAttachmentService

    monkeypatch.setattr(ComplaintService, "_build_complaint_view_url", lambda self, cid, base_url_override=None: "")
    monkeypatch.setattr(StockInquiryService, "_build_stock_inquiry_view_url", lambda self, iid, base_url_override=None: "")
    monkeypatch.setattr(EntityAttachmentService, "list_links", lambda self, et, eid: [])
