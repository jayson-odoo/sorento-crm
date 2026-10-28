"""Staff routes for the comment thread on a submitted form.

GET|POST /form-comments/{kind}/{entity_id}. The kind's own view permission gates both verbs
(there is no single slug that covers four kinds), and POST needs a staff session (no API key).
A request form's `view_own` alone reads (never writes) the rows their own contact submitted (PORTAL-P4).
Plan: documentation/plans/forms/PLAN-form-comments-09oct.md
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services import own_scope
from app.services.error_handler import handle_not_found, handle_unprocessable
from app.services.form_comment_service import FORM_COMMENT_KINDS, VIEW_PERMISSION, FormCommentService
from app.services.user_service import UserPermissionService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

_VIEW_PERMISSION = VIEW_PERMISSION


_MODULE = {"complaint": "complaints", "sample_request": "projects"}  # every other kind is procurement
MAX_FILES = 5
MAX_FILE_BYTES = 25 * 1024 * 1024


def _check_module(kind: str, user_id: str, db: Session) -> None:
    """Per-kind module gate (the router guard only checks that either module is on)."""
    if not getattr(settings, "module_guard_strict", False):
        return
    from app.modules.runtime.installer import DEFAULT_TENANT_ID, is_module_enabled, tenant_has_any_module_row

    service = UserPermissionService(db)
    if service.get_user_role_slugs(user_id) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return
    module = _MODULE.get(kind, "procurement")
    if tenant_has_any_module_row(db, DEFAULT_TENANT_ID) and not is_module_enabled(db, DEFAULT_TENANT_ID, module):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Module not enabled: {module}")


async def read_uploads(files: Optional[list[UploadFile]]) -> list:
    """Files as (name, bytes, type). Count and size are checked BEFORE any part is read."""
    named = [f for f in (files or []) if f.filename]
    if len(named) > MAX_FILES:
        raise handle_unprocessable(f"At most {MAX_FILES} files per comment.")
    for f in named:
        if f.size is not None and f.size > MAX_FILE_BYTES:
            raise handle_unprocessable("File is too large.")
    return [(f.filename, await f.read(), f.content_type) for f in named]


def _authorize(kind: str, entity_id: str, current_user: dict, db: Session, *, write: bool = False) -> str:
    if kind not in FORM_COMMENT_KINDS:
        raise handle_unprocessable(f"Unsupported form type: {kind!r}.")
    slug = _VIEW_PERMISSION[kind]
    perms = UserPermissionService(db)
    if perms.check_user_has_permission(current_user["id"], slug):
        _check_module(kind, current_user["id"], db)
        return validate_uuid_path(entity_id, resource="Form")
    # A request form's `view_own` alone READS the thread on their own row only (PORTAL-P4-REQUESTS).
    # A staff comment WhatsApps the submitter, who is them: they write through /my-requests.
    view_own = own_scope.REQUEST_KINDS.get(kind, (None, None))[1]
    if write or not view_own or not perms.check_user_has_permission(current_user["id"], view_own):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {slug}")
    _check_module(kind, current_user["id"], db)
    eid = validate_uuid_path(entity_id, resource="Form")
    if not own_scope.request_in_scope(db, kind, eid, own_scope.me(db, current_user["id"])):
        raise handle_not_found("Form", eid)
    return eid


@router.get("/{kind}/{entity_id}")
def list_form_comments(
    kind: str,
    entity_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    eid = _authorize(kind, entity_id, current_user, db)
    svc = FormCommentService(db)
    return {"items": svc.list_comments(kind, eid, svc.staff_viewer(current_user))}


@router.post("/{kind}/{entity_id}", status_code=status.HTTP_201_CREATED)
async def add_form_comment(
    kind: str,
    entity_id: str,
    body: Annotated[str, Form()] = "",
    files: Annotated[Optional[list[UploadFile]], File()] = None,
    parent_id: Annotated[Optional[str], Form()] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    eid = _authorize(kind, entity_id, current_user, db, write=True)
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    uploads = await read_uploads(files)
    return FormCommentService(db).add_staff_comment(kind, eid, user, body, uploads, parent_id=parent_id or None)


class EditCommentBody(BaseModel):
    body: str = ""


@router.patch("/{kind}/{entity_id}/comments/{comment_id}")
def edit_form_comment(
    kind: str,
    entity_id: str,
    comment_id: str,
    payload: EditCommentBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    eid = _authorize(kind, entity_id, current_user, db, write=True)
    svc = FormCommentService(db)
    return {"comment": svc.edit_comment(kind, eid, comment_id, svc.staff_viewer(current_user), payload.body)}
