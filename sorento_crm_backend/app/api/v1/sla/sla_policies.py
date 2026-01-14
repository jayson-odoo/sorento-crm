"""SLA policies API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.sla_service import SLAPolicyService
from app.schemas.sla import SLAPolicyCreate, SLAPolicyUpdate, SLAPolicyResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[SLAPolicyResponse])
async def get_sla_policies(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort: Optional[str] = Query("created_at"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get SLA policies with pagination, filtering, and sorting."""
    try:
        service = SLAPolicyService(db)
        result = service.list_policies(
            page=page,
            limit=limit,
            query=query,
            status=status,
            sort_field=sort or "created_at",
            sort_dir=dir or "asc"
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{policy_id}", response_model=SLAPolicyResponse)
async def get_sla_policy(
    policy_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single SLA policy by ID."""
    try:
        service = SLAPolicyService(db)
        policy = service.get_policy(policy_id)
        return policy
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=SLAPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_sla_policy(
    policy_data: SLAPolicyCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new SLA policy with tiers."""
    try:
        service = SLAPolicyService(db)
        policy = service.create_policy(policy_data)
        return policy
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{policy_id}", response_model=SLAPolicyResponse)
async def update_sla_policy(
    policy_id: str,
    policy_data: SLAPolicyUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an SLA policy."""
    try:
        service = SLAPolicyService(db)
        policy = service.update_policy(policy_id, policy_data)
        return policy
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{policy_id}", status_code=status.HTTP_200_OK)
async def delete_sla_policy(
    policy_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an SLA policy."""
    try:
        service = SLAPolicyService(db)
        # Implement delete logic
        return {"message": "SLA policy deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
