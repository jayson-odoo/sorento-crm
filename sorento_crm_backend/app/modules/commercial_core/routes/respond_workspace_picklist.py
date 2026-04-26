"""Active Respond workspaces for commercial lead forms (dropdown)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.respond_workspace import RespondWorkspaceSelectItem
from app.services.respond_workspace_service import RespondWorkspaceService
from app.services.user_service import UserPermissionService

router = APIRouter()


def _require_leads_view(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    svc = UserPermissionService(db)
    uid = current_user["id"]
    if svc.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
        return current_user
    if not svc.check_user_has_permission(uid, "commercial_core.leads.view"):
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission required: commercial_core.leads.view")
    return current_user


@router.get("/respond-workspaces/select", response_model=list[RespondWorkspaceSelectItem])
async def list_respond_workspaces_for_select(
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    svc = RespondWorkspaceService(db)
    rows = svc.list_active_select()
    return [RespondWorkspaceSelectItem.model_validate(r) for r in rows]
