"""Activity + internal-note threads on projects, master quotations, and leads."""
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.schemas.entity_conversation import (
    ConversationMessageCreate,
    ConversationMessageOut,
)
from app.modules.commercial_core.services.entity_conversation_service import (
    ENTITY_COMMERCIAL_LEAD,
    ENTITY_MASTER_QUOTATION,
    ENTITY_MASTER_QUOTATION_TASK,
    ENTITY_PROJECT,
    ENTITY_PROJECT_TASK,
    assert_master_contains_task,
    assert_project_contains_task,
    create_message,
    list_messages,
)
from app.services.error_handler import handle_internal_error
from app.services.user_service import UserPermissionService

router = APIRouter()


def _require(perm: str):
    async def _inner(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
        svc = UserPermissionService(db)
        uid = current_user["id"]
        if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
            return current_user
        if not svc.check_user_has_permission(uid, perm):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {perm}")
        return current_user

    return _inner


@router.get(
    "/projects/{project_id}/conversation-messages",
    response_model=List[ConversationMessageOut],
)
async def list_project_messages(
    project_id: str,
    scope: Literal["activity", "internal_note"] = Query("activity"),
    _user: dict = Depends(_require("commercial_core.projects.view")),
    db: Session = Depends(get_db),
):
    try:
        return list_messages(
            db,
            entity_type=ENTITY_PROJECT,
            entity_id=project_id,
            scope=scope,
            viewer_user_id=_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/projects/{project_id}/conversation-messages",
    response_model=ConversationMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_project_message(
    project_id: str,
    body: ConversationMessageCreate,
    current_user: dict = Depends(_require("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
):
    try:
        return create_message(
            db,
            entity_type=ENTITY_PROJECT,
            entity_id=project_id,
            scope=body.scope,
            body_html=body.body_html,
            author_user_id=current_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/leads/{lead_id}/conversation-messages",
    response_model=List[ConversationMessageOut],
)
async def list_lead_messages(
    lead_id: str,
    scope: Literal["activity", "internal_note"] = Query("activity"),
    _user: dict = Depends(_require("commercial_core.leads.view")),
    db: Session = Depends(get_db),
):
    try:
        return list_messages(
            db,
            entity_type=ENTITY_COMMERCIAL_LEAD,
            entity_id=lead_id,
            scope=scope,
            viewer_user_id=_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/leads/{lead_id}/conversation-messages",
    response_model=ConversationMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_lead_message(
    lead_id: str,
    body: ConversationMessageCreate,
    current_user: dict = Depends(_require("commercial_core.leads.edit")),
    db: Session = Depends(get_db),
):
    try:
        return create_message(
            db,
            entity_type=ENTITY_COMMERCIAL_LEAD,
            entity_id=lead_id,
            scope=body.scope,
            body_html=body.body_html,
            author_user_id=current_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/master-quotations/{master_id}/conversation-messages",
    response_model=List[ConversationMessageOut],
)
async def list_master_quotation_messages(
    master_id: str,
    scope: Literal["activity", "internal_note"] = Query("activity"),
    _user: dict = Depends(_require("commercial_core.master_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        return list_messages(
            db,
            entity_type=ENTITY_MASTER_QUOTATION,
            entity_id=master_id,
            scope=scope,
            viewer_user_id=_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/conversation-messages",
    response_model=ConversationMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_master_quotation_message(
    master_id: str,
    body: ConversationMessageCreate,
    current_user: dict = Depends(_require("commercial_core.master_quotations.edit")),
    db: Session = Depends(get_db),
):
    try:
        return create_message(
            db,
            entity_type=ENTITY_MASTER_QUOTATION,
            entity_id=master_id,
            scope=body.scope,
            body_html=body.body_html,
            author_user_id=current_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/projects/{project_id}/tasks/{task_id}/conversation-messages",
    response_model=List[ConversationMessageOut],
)
async def list_project_task_messages(
    project_id: str,
    task_id: str,
    scope: Literal["activity", "internal_note"] = Query("activity"),
    _user: dict = Depends(_require("commercial_core.projects.view")),
    db: Session = Depends(get_db),
):
    try:
        assert_project_contains_task(db, project_id, task_id)
        return list_messages(
            db,
            entity_type=ENTITY_PROJECT_TASK,
            entity_id=task_id,
            scope=scope,
            viewer_user_id=_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/projects/{project_id}/tasks/{task_id}/conversation-messages",
    response_model=ConversationMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_project_task_message(
    project_id: str,
    task_id: str,
    body: ConversationMessageCreate,
    current_user: dict = Depends(_require("commercial_core.projects.edit")),
    db: Session = Depends(get_db),
):
    try:
        assert_project_contains_task(db, project_id, task_id)
        return create_message(
            db,
            entity_type=ENTITY_PROJECT_TASK,
            entity_id=task_id,
            scope=body.scope,
            body_html=body.body_html,
            author_user_id=current_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get(
    "/master-quotations/{master_id}/tasks/{task_id}/conversation-messages",
    response_model=List[ConversationMessageOut],
)
async def list_master_quotation_task_messages(
    master_id: str,
    task_id: str,
    scope: Literal["activity", "internal_note"] = Query("activity"),
    _user: dict = Depends(_require("commercial_core.master_quotations.view")),
    db: Session = Depends(get_db),
):
    try:
        assert_master_contains_task(db, master_id, task_id)
        return list_messages(
            db,
            entity_type=ENTITY_MASTER_QUOTATION_TASK,
            entity_id=task_id,
            scope=scope,
            viewer_user_id=_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post(
    "/master-quotations/{master_id}/tasks/{task_id}/conversation-messages",
    response_model=ConversationMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_master_quotation_task_message(
    master_id: str,
    task_id: str,
    body: ConversationMessageCreate,
    current_user: dict = Depends(_require("commercial_core.master_quotations.edit")),
    db: Session = Depends(get_db),
):
    try:
        assert_master_contains_task(db, master_id, task_id)
        return create_message(
            db,
            entity_type=ENTITY_MASTER_QUOTATION_TASK,
            entity_id=task_id,
            scope=body.scope,
            body_html=body.body_html,
            author_user_id=current_user["id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
