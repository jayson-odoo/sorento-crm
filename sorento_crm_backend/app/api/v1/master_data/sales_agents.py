"""Sales agents — read-only AutoCount mirror + annotation (Slice 2)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.dependencies import require_permission, require_permission_with_api_key
from app.models.sales_agent import SalesAgent
from app.schemas.autocount_mirror import MirrorAnnotationUpdate, SalesAgentResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.autocount_mirror_service import MirrorReadService
from app.services.error_handler import handle_internal_error
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()
_RESOURCE = "Sales Agent"


@router.get("/", response_model=ListResponse[SalesAgentResponse])
async def list_sales_agents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: str = Query("desc"),
    current_user: dict = Depends(require_permission_with_api_key("master_data.sales_agents.view")),
    db: Session = Depends(get_db),
):
    try:
        return MirrorReadService(db).list(
            SalesAgent,
            search_columns=[SalesAgent.sales_agent, SalesAgent.description],
            page=page, limit=limit, query=query, sort=sort, dir=dir,
        )
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{sales_agent_id}", response_model=SalesAgentResponse)
async def get_sales_agent(
    sales_agent_id: str,
    current_user: dict = Depends(require_permission_with_api_key("master_data.sales_agents.view")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(sales_agent_id, resource=_RESOURCE)
        return MirrorReadService(db).get(SalesAgent, sales_agent_id, resource=_RESOURCE)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.patch("/{sales_agent_id}/annotation", response_model=SalesAgentResponse)
async def annotate_sales_agent(
    sales_agent_id: str,
    payload: MirrorAnnotationUpdate,
    current_user: dict = Depends(require_permission("master_data.sales_agents.edit")),
    db: Session = Depends(get_db),
):
    try:
        validate_uuid_path(sales_agent_id, resource=_RESOURCE)
        fields = payload.model_fields_set
        return MirrorReadService(db).annotate(
            SalesAgent, sales_agent_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
