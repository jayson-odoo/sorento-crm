"""Sales agents - read-only AutoCount mirror + annotation (Slice 2 / SCM S6).

Deliberately not a CRUD master. There is no create and no delete: a row appears when an
upload meets a code no one holds (`sales_agent_service.resolve_or_create`), which is the
only place the codes are ever known, and deleting one would orphan the orders that name
it. What a human does here is annotate: say who the code belongs to, say what its orders
are for, and retire a code nobody sells under any more (`is_active`, which is what the
Agent pickers filter on - see `SalesAgentAnnotationUpdate` for why that one field is
sales-agent-only).

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
from app.schemas.autocount_mirror import (
    BulkAnnotateResult,
    SalesAgentAnnotationUpdate,
    SalesAgentBulkAnnotate,
    SalesAgentResponse,
)
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.schemas.order import CustomerResponse
from app.schemas.contact_customer import AgentCustomerAssign
from app.services.autocount_mirror_service import MirrorReadService
from app.services import contact_customer_service
from app.services.error_handler import handle_internal_error, handle_not_found
from app.services.order_service import CustomerService
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


@router.post("/bulk-annotate", response_model=BulkAnnotateResult)
async def bulk_annotate_sales_agents(
    payload: SalesAgentBulkAnnotate,
    current_user: dict = Depends(require_permission("master_data.sales_agents.edit")),
    db: Session = Depends(get_db),
):
    """Set one annotation across a selection.

    Declared before `/{sales_agent_id}` so `bulk-annotate` never parses as an id, and gated
    on the SAME permission as the single-row PATCH: reclassifying 38 agents at once is the
    same write, not a bigger one, and a role that may not do it once may not do it in bulk.

    One transaction: `sales_agent_service.annotate_many` flushes, and the commit is here, so
    a class the fulfilment policy cannot weigh (or an id that no longer resolves) leaves the
    whole selection untouched rather than classifying half of it.
    """
    try:
        fields = payload.model_fields_set
        updated = sales_agent_service.annotate_many(
            db, payload.sales_agent_ids,
            demand_class=payload.demand_class,
            write_demand_class="demand_class" in fields,
            location_group=payload.location_group,
            write_location_group="location_group" in fields,
        )
        db.commit()
        return {"updated": updated}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
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
    payload: SalesAgentAnnotationUpdate,
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
            aliases=payload.aliases, write_aliases="aliases" in fields,
            demand_class=payload.demand_class, write_demand_class="demand_class" in fields,
            location_group=payload.location_group,
            write_location_group="location_group" in fields,
            contact_id=payload.contact_id,
            write_contact_id="contact_id" in fields,
        )
        # Retiring a code. Written here rather than in `MirrorReadService.annotate`, which
        # is shared with the entities whose `is_active` is synced - see
        # `SalesAgentAnnotationUpdate` - and inside the same uncommitted transaction as the
        # class above, so a refused class leaves the row active exactly as it was.
        if "is_active" in fields:
            agent.is_active = bool(payload.is_active)
            db.flush()
        return service.annotate(
            SalesAgent, sales_agent_id, resource=_RESOURCE,
            internal_note=payload.internal_note, follow_up=payload.follow_up,
            set_note="internal_note" in fields, set_follow_up="follow_up" in fields,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{sales_agent_id}/customers", response_model=ListResponse[CustomerResponse])
async def list_sales_agent_customers(
    sales_agent_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: str = Query("customer_code"),
    dir: str = Query("asc"),
    current_user: dict = Depends(require_permission("master_data.sales_agents.view")),
    db: Session = Depends(get_db),
):
    """The customers this agent handles, under the caller's company scope."""
    try:
        validate_uuid_path(sales_agent_id, resource=_RESOURCE)
        MirrorReadService(db).get(SalesAgent, sales_agent_id, resource=_RESOURCE)
        return CustomerService(db).list_customers(
            page=page, limit=limit, query=query, sort_field=sort, sort_dir=dir,
            sales_agent_id=sales_agent_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{sales_agent_id}/customers", response_model=CustomerResponse)
async def assign_sales_agent_customer(
    sales_agent_id: str,
    payload: AgentCustomerAssign,
    current_user: dict = Depends(require_permission("master_data.sales_agents.edit")),
    db: Session = Depends(get_db),
):
    """Move a customer to this agent, from another agent too."""
    try:
        validate_uuid_path(sales_agent_id, resource=_RESOURCE)
        MirrorReadService(db).get(SalesAgent, sales_agent_id, resource=_RESOURCE)
        customer = contact_customer_service.get_customer_in_scope(db, payload.customer_id)
        if customer is None:
            raise handle_not_found("Customer", payload.customer_id)
        return CustomerService(db).assign_sales_agent(customer.id, sales_agent_id)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise handle_internal_error(str(e))
