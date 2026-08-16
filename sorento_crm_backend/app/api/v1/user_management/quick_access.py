"""Quick access (pinned menu items and folders) API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.services.uuid_path_param import validate_uuid_path
from app.dependencies import get_current_user, require_permission
from app.models.user import UserQuickAccess
from app.services.error_handler import handle_internal_error

router = APIRouter()


class QuickAccessCreate(BaseModel):
    path: str
    label: Optional[str] = None


class QuickAccessResponse(BaseModel):
    id: str
    path: str
    label: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True


class QuickAccessReorderRequest(BaseModel):
    ordered_ids: list[str]


def _get_next_sort_order(db: Session, user_id: str) -> int:
    r = db.query(UserQuickAccess).filter(UserQuickAccess.user_id == user_id).count()
    return r


# Intentionally stays on `get_current_user`: the read is self-scoped to
# `current_user["id"]` (same family as `GET /users/me`) and the app shell fires it on
# every page load for every user, so a permission gate would 403 users who simply hold
# no pin/unpin grant. The sibling writes are gated on `menu.quick_access.pin` /
# `.unpin`. See `documentation/plans/security/PLAN-user-management-read-gates.md`.
@router.get("/", response_model=list[QuickAccessResponse])
async def list_quick_access(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List current user's quick access entries ordered by sort_order."""
    try:
        rows = (
            db.query(UserQuickAccess)
            .filter(UserQuickAccess.user_id == current_user["id"])
            .order_by(UserQuickAccess.sort_order.asc(), UserQuickAccess.path.asc())
            .all()
        )
        return [QuickAccessResponse.model_validate(r) for r in rows]
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=QuickAccessResponse, status_code=status.HTTP_201_CREATED)
async def add_quick_access(
    body: QuickAccessCreate,
    current_user: dict = Depends(require_permission("menu.quick_access.pin")),
    db: Session = Depends(get_db),
):
    """Add a quick access entry (menu path or folder URL). If path already exists for user, no-op and return existing."""
    try:
        path = (body.path or "").strip()
        if not path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="path is required")
        existing = (
            db.query(UserQuickAccess)
            .filter(
                UserQuickAccess.user_id == current_user["id"],
                UserQuickAccess.path == path,
            )
            .first()
        )
        if existing:
            return QuickAccessResponse.model_validate(existing)
        sort_order = _get_next_sort_order(db, current_user["id"])
        row = UserQuickAccess(
            user_id=current_user["id"],
            path=path,
            label=body.label.strip() if body.label else None,
            sort_order=sort_order,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return QuickAccessResponse.model_validate(row)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.patch("/reorder", response_model=list[QuickAccessResponse])
async def reorder_quick_access(
    body: QuickAccessReorderRequest = Body(...),
    current_user: dict = Depends(require_permission("menu.quick_access.pin")),
    db: Session = Depends(get_db),
):
    """Update sort_order by passing ordered list of entry ids. Only ids belonging to current user are updated."""
    try:
        user_id = current_user["id"]
        ordered_ids = body.ordered_ids or []
        if not ordered_ids:
            rows = (
                db.query(UserQuickAccess)
                .filter(UserQuickAccess.user_id == user_id)
                .order_by(UserQuickAccess.sort_order.asc(), UserQuickAccess.path.asc())
                .all()
            )
            return [QuickAccessResponse.model_validate(r) for r in rows]
        # Fetch all user entries and build id -> row map
        rows = db.query(UserQuickAccess).filter(UserQuickAccess.user_id == user_id).all()
        by_id = {r.id: r for r in rows}
        for idx, eid in enumerate(ordered_ids):
            if eid in by_id:
                by_id[eid].sort_order = idx
        db.commit()
        # Return in new order
        out = []
        for eid in ordered_ids:
            if eid in by_id:
                db.refresh(by_id[eid])
                out.append(QuickAccessResponse.model_validate(by_id[eid]))
        # Append any not in ordered_ids (shouldn't happen in normal UI)
        for r in rows:
            if r.id not in ordered_ids:
                db.refresh(r)
                out.append(QuickAccessResponse.model_validate(r))
        out.sort(key=lambda x: (x.sort_order, x.path))
        return out
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_quick_access(
    entry_id: str,
    current_user: dict = Depends(require_permission("menu.quick_access.unpin")),
    db: Session = Depends(get_db),
):
    """Remove one quick access entry by id (must belong to current user)."""
    try:
        validate_uuid_path(entry_id, resource="Quick Access Entry")
        row = (
            db.query(UserQuickAccess)
            .filter(
                UserQuickAccess.id == entry_id,
                UserQuickAccess.user_id == current_user["id"],
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quick access entry not found")
        db.delete(row)
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
