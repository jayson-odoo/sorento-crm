"""Search respond_contacts within a workspace (lead contact picker)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.commercial_core.schemas.lead_respond_contact import RespondContactBrief
from app.modules.commercial_core.services.lead_respond_contact_service import LeadRespondContactService
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


@router.get("/respond-contacts/search", response_model=list[RespondContactBrief])
async def search_respond_contacts(
    workspace_id: str = Query(..., description="Respond workspace UUID"),
    q: Optional[str] = Query(None, description="Phone or name substring"),
    limit: int = Query(50, ge=1, le=200),
    _user: dict = Depends(_require_leads_view),
    db: Session = Depends(get_db),
):
    svc = LeadRespondContactService(db)
    contacts = svc.search_contacts(workspace_id, q=q, limit=limit)
    return [
        RespondContactBrief(
            id=str(c.id),
            phone_number=c.phone_number,
            name=c.name,
            first_name=getattr(c, "first_name", None),
            last_name=getattr(c, "last_name", None),
            respond_io_id=getattr(c, "respond_io_id", None),
            access_type_code=getattr(c, "access_type_code", None),
            respond_workspace_id=str(c.respond_workspace_id),
        )
        for c in contacts
    ]
