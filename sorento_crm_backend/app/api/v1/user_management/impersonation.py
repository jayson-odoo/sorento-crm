"""Admin impersonation routes.

An admin (real user) can temporarily browse the system as another non-admin user
to verify access rights. The effective user is signaled via the
``X-Impersonate-User-Id`` request header, which is honored by ``get_current_user``
when an active ``impersonation_sessions`` row exists for that admin/target pair.

Audit / created_by / updated_by always remain the real admin — see
``app.dependencies.get_actor_user_id`` and ``set_audit_context``.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_real_user
from app.models.impersonation import ImpersonationSession
from app.models.user import User
from app.services.audit_service import log_audit
from app.services.user_avatar_url import resolve_avatar_url_for_client
from app.services.user_service import UserPermissionService

logger = logging.getLogger(__name__)

router = APIRouter()


class StartImpersonationRequest(BaseModel):
    target_user_id: str


class TargetUserSummary(BaseModel):
    id: str
    name: Optional[str]
    email: Optional[str]
    avatar: Optional[str]
    role_name: Optional[str]


class ImpersonationSessionResponse(BaseModel):
    session_id: str
    started_at: datetime
    target_user: TargetUserSummary


def _ensure_admin(db: Session, real_user: dict) -> set[str]:
    role_slugs = UserPermissionService(db).get_user_role_slugs(real_user["id"])
    admin_set = {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}
    if not (role_slugs & admin_set):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can impersonate users",
        )
    return role_slugs


def _serialize_target(db: Session, target: User) -> TargetUserSummary:
    from app.models.user import UserRole, UserRoleAssignment

    slug = (
        db.query(UserRole.slug)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == UserRole.id)
        .filter(UserRoleAssignment.user_id == target.id)
        .order_by(UserRoleAssignment.assigned_at.asc())
        .first()
    )
    try:
        avatar_url = resolve_avatar_url_for_client(
            target.avatar,
            getattr(target, "avatar_storage_provider", None),
        )
    except Exception:
        avatar_url = target.avatar
    return TargetUserSummary(
        id=target.id,
        name=target.name,
        email=target.email,
        avatar=avatar_url,
        role_name=slug[0] if slug else None,
    )


def _serialize_session(db: Session, row: ImpersonationSession, target: User) -> ImpersonationSessionResponse:
    return ImpersonationSessionResponse(
        session_id=row.id,
        started_at=row.started_at,
        target_user=_serialize_target(db, target),
    )


@router.post("/start", response_model=ImpersonationSessionResponse)
async def start_impersonation(
    body: StartImpersonationRequest,
    request: Request,
    real_user: dict = Depends(get_real_user),
    db: Session = Depends(get_db),
) -> ImpersonationSessionResponse:
    _ensure_admin(db, real_user)
    target_id = body.target_user_id
    if not target_id or target_id == real_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

    target = db.query(User).filter(User.id == target_id).first()
    if not target or target.is_trashed:
        raise HTTPException(status_code=404, detail="Target user not found")
    if target.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="Target user is not active")

    target_slugs = UserPermissionService(db).get_user_role_slugs(target.id)
    if target_slugs & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Cannot impersonate another admin or superadmin",
        )

    # Defensive: end any existing active session for this admin so the partial
    # unique index never blocks us.
    db.query(ImpersonationSession).filter(
        ImpersonationSession.admin_user_id == real_user["id"],
        ImpersonationSession.ended_at.is_(None),
    ).update({"ended_at": datetime.utcnow()}, synchronize_session=False)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    row = ImpersonationSession(
        admin_user_id=real_user["id"],
        target_user_id=target.id,
        started_ip=ip,
        started_user_agent=(ua or "")[:500] or None,
    )
    db.add(row)
    db.flush()

    log_audit(
        db,
        entity_type="impersonation_session",
        entity_id=row.id,
        action="CREATE",
        user_id=real_user["id"],
        description="impersonation_start",
        new_values={
            "admin_user_id": real_user["id"],
            "target_user_id": target.id,
            "target_email": target.email,
        },
        ip_address=ip,
    )
    db.commit()
    db.refresh(row)

    return _serialize_session(db, row, target)


@router.post("/stop")
async def stop_impersonation(
    request: Request,
    real_user: dict = Depends(get_real_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ImpersonationSession)
        .filter(
            ImpersonationSession.admin_user_id == real_user["id"],
            ImpersonationSession.ended_at.is_(None),
        )
        .first()
    )
    if not row:
        return {"ended": False}
    row.ended_at = datetime.utcnow()
    db.flush()
    log_audit(
        db,
        entity_type="impersonation_session",
        entity_id=row.id,
        action="UPDATE",
        user_id=real_user["id"],
        description="impersonation_end",
        new_values={
            "admin_user_id": real_user["id"],
            "target_user_id": row.target_user_id,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"ended": True, "session_id": row.id}


@router.get("/current", response_model=Optional[ImpersonationSessionResponse])
async def current_impersonation(
    real_user: dict = Depends(get_real_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ImpersonationSession)
        .filter(
            ImpersonationSession.admin_user_id == real_user["id"],
            ImpersonationSession.ended_at.is_(None),
        )
        .first()
    )
    if not row:
        return None
    target = db.query(User).filter(User.id == row.target_user_id).first()
    if not target:
        return None
    return _serialize_session(db, row, target)
