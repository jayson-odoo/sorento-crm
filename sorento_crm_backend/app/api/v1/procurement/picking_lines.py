"""Picking lines (GRN lines) API routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.services.procurement_service import PickingHeaderService
from app.schemas.procurement import PickingLineResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/", response_model=ListResponse[PickingLineResponse])
async def get_picking_lines(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None, description="Search by SPO allocation or product"),
    sort: Optional[str] = Query("spo_allocation"),
    dir: Optional[str] = Query("asc"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List picking lines with pagination, search (SPO allocation or product), and sort."""
    try:
        service = PickingHeaderService(db)
        return service.list_picking_lines(
            page=page,
            limit=limit,
            query=query,
            sort_field=sort or "spo_allocation",
            sort_dir=dir or "asc",
        )
    except Exception as e:
        raise handle_internal_error(str(e))
