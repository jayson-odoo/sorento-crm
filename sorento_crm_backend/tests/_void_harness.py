"""Shared harness for the form-void test suite (not collected by pytest).

Yields a blank Postgres session over the real schema, a TestClient wired to a
dynamic actor, and grant-based permission stubbing.

This used to build an in-memory sqlite session, which required rewriting
JSONB/ARRAY columns to generic JSON and discarding Postgres-only partial
indexes. Those rewrites mutated the shared model metadata **permanently and
process-wide**: once any void test ran, every later test in the same pytest
process bound JSON into columns Postgres types as ``varchar[]``, failing with
"column is of type character varying[] but expression is of type json". The
symptom appeared in unrelated files (SLA takeover, prompt registry) and only
in full-suite runs, never in isolation. Nothing to shim now -- the real schema
has the real types.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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
from sqlalchemy.orm import Session

from tests._pg_fixture import blank_schema_engine


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


def _clear(session) -> None:
    """Empty this harness's tables, children before parents."""
    for model in reversed(_MODELS):
        session.query(model).delete(synchronize_session=False)
    session.commit()


def make_session():
    """A session over the blank schema, with this harness's tables emptied.

    Bound to the engine rather than to a held-open connection: these tests
    commit, and pinning one connection per session exhausted the pool and hung
    the run.

    Because the writes really are committed, isolation has to be explicit at
    BOTH ends. Clearing only on the way in still left the last void test's rows
    in the shared schema, which broke test_sla_kpi -- it counts SLA rows, and
    this harness owns several SLA tables. So close() clears on the way out too.
    """
    session = Session(bind=blank_schema_engine(), autoflush=False)
    _clear(session)

    original_close = session.close

    def close_and_clear(*args, **kwargs):
        try:
            session.rollback()
            _clear(session)
        except Exception:
            pass
        return original_close(*args, **kwargs)

    session.close = close_and_clear  # type: ignore[method-assign]
    return session


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
