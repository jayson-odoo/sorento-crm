"""List and post activity / internal notes for projects, master quotations, leads, and per-task threads."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_activity.models import CommercialProjectTask
from app.models.entity_conversation import EntityConversationMessage
from app.modules.commercial_core.services.commercial_lead_service import CommercialLeadService
from app.modules.commercial_core.services.commercial_project_service import CommercialProjectService
from app.modules.commercial_core.services.commercial_quotation_revision_service import CommercialQuotationRevisionService

SCOPE_ACTIVITY = "activity"
SCOPE_INTERNAL = "internal_note"

ENTITY_PROJECT = "commercial_project"
ENTITY_MASTER_QUOTATION = "commercial_master_quotation"
ENTITY_COMMERCIAL_LEAD = "commercial_lead"
ENTITY_PROJECT_TASK = "commercial_project_task"
ENTITY_MASTER_QUOTATION_TASK = "commercial_master_quotation_task"


def _task_ids_in_board(task_board: Any) -> set[str]:
    if not isinstance(task_board, dict):
        return set()
    tasks = task_board.get("tasks") or []
    out: set[str] = set()
    for t in tasks:
        if isinstance(t, dict) and t.get("id"):
            out.add(str(t["id"]))
    return out


def assert_project_contains_task(db: Session, project_id: str, task_id: str) -> None:
    CommercialProjectService(db).get_project(project_id)
    row = (
        db.query(CommercialProjectTask)
        .filter(
            CommercialProjectTask.id == task_id,
            CommercialProjectTask.project_id == project_id,
            CommercialProjectTask.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found on this project.")


def assert_master_contains_task(db: Session, master_id: str, task_id: str) -> None:
    mq = CommercialQuotationRevisionService(db).get_master_by_id(master_id)
    tb = dict(mq.task_board or {})
    if task_id not in _task_ids_in_board(tb):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found on this quotation.")


def _strip_html_to_text(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()


def _serialize_message(row: EntityConversationMessage) -> Dict[str, Any]:
    author_out = None
    if row.author_user_id and row.author:
        author_out = {
            "id": row.author_user_id,
            "name": (row.author.name or "").strip() or None,
            "email": row.author.email or None,
        }
    return {
        "id": row.id,
        "scope": row.scope,
        "is_system": bool(row.is_system),
        "body_html": row.body_html or "",
        "author": author_out,
        "created_at": row.created_at,
    }


def list_messages(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    scope: Literal["activity", "internal_note"],
    viewer_user_id: str,
) -> List[Dict[str, Any]]:
    if entity_type == ENTITY_PROJECT:
        CommercialProjectService(db).get_project(entity_id)
    elif entity_type == ENTITY_MASTER_QUOTATION:
        CommercialQuotationRevisionService(db).get_master_by_id(entity_id)
    elif entity_type == ENTITY_COMMERCIAL_LEAD:
        CommercialLeadService(db).get_lead(entity_id)
    elif entity_type in (ENTITY_PROJECT_TASK, ENTITY_MASTER_QUOTATION_TASK):
        pass  # Caller must validate task belongs to parent (see API routes).
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported entity_type.")

    q = (
        db.query(EntityConversationMessage)
        .options(joinedload(EntityConversationMessage.author))
        .filter(
            EntityConversationMessage.entity_type == entity_type,
            EntityConversationMessage.entity_id == entity_id,
        )
    )
    if scope == SCOPE_INTERNAL:
        q = q.filter(
            EntityConversationMessage.scope == SCOPE_INTERNAL,
            EntityConversationMessage.author_user_id == viewer_user_id,
        )
    else:
        q = q.filter(EntityConversationMessage.scope == SCOPE_ACTIVITY)
    rows = q.order_by(EntityConversationMessage.created_at.asc()).all()
    return [_serialize_message(r) for r in rows]


def create_message(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    scope: Literal["activity", "internal_note"],
    body_html: str,
    author_user_id: str,
) -> Dict[str, Any]:
    plain = _strip_html_to_text(body_html)
    if not plain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty.",
        )

    if entity_type == ENTITY_PROJECT:
        CommercialProjectService(db).get_project(entity_id)
    elif entity_type == ENTITY_MASTER_QUOTATION:
        CommercialQuotationRevisionService(db).get_master_by_id(entity_id)
    elif entity_type == ENTITY_COMMERCIAL_LEAD:
        CommercialLeadService(db).get_lead(entity_id)
    elif entity_type in (ENTITY_PROJECT_TASK, ENTITY_MASTER_QUOTATION_TASK):
        pass  # Caller must validate task belongs to parent (see API routes).
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported entity_type.")

    row = EntityConversationMessage(
        entity_type=entity_type,
        entity_id=entity_id,
        scope=scope,
        is_system=False,
        body_html=body_html,
        author_user_id=author_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row = (
        db.query(EntityConversationMessage)
        .options(joinedload(EntityConversationMessage.author))
        .filter(EntityConversationMessage.id == row.id)
        .first()
    )
    return _serialize_message(row)


def append_system_message(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    body_html: str,
) -> None:
    """Optional: workflow hooks can record system-visible lines in the activity feed.

    Persists the row with ``flush()`` only; the caller's transaction must ``commit()``.
    """
    plain = _strip_html_to_text(body_html)
    if not plain:
        return
    row = EntityConversationMessage(
        entity_type=entity_type,
        entity_id=entity_id,
        scope=SCOPE_ACTIVITY,
        is_system=True,
        body_html=body_html,
        author_user_id=None,
    )
    db.add(row)
    db.flush()
