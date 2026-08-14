"""Sales agents - read-only AutoCount mirror + annotation (Slice 2 / SCM S6).

Deliberately not a CRUD master. There is no create and no delete: a row appears when an
upload meets a code no one holds (`sales_agent_service.resolve_or_create`), which is the
only place the codes are ever known, and deleting one would orphan the orders that name
it. What a human does here is annotate: say who the code belongs to, and say what its
orders are for.

The list and detail reads are `MirrorReadService`, the same generic reader every other
mirror entity uses. The annotation adds `person_label` and `demand_class` to the two
columns that service already writes; the class itself is validated by
`sales_agent_service`, never here, so the closed vocabulary lives in one place and the
message an admin sees names the words the fulfilment policy can actually weigh.
"""
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
from app.services.scm import sales_agent_service
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
        service = MirrorReadService(db)
        # The agent-specific columns first, flushed and not committed, so a class the
        # policy cannot weigh refuses the whole save instead of leaving the note written
        # and the class not.
        agent = service.get(SalesAgent, sales_agent_id, resource=_RESOURCE)
        sales_agent_service.annotate(
            db, agent,
            person_label=payload.person_label, write_person_label="person_label" in fields,
            demand_class=payload.demand_class, write_demand_class="demand_class" in fields,
        )
        return service.annotate(
            SalesAgent, sales_agent_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
