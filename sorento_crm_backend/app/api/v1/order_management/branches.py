"""Customer Branches (#1356): read-only list of the AutoCount branch table.

AutoCount is the source of truth (plan 1.11, ruling Q2): the ingest is the only writer, so
there is no create, update or delete route here.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.autocount_branch import BranchResponse
from app.schemas.common import ListResponse, MAX_PAGE_LIMIT
from app.services.branch_service import BranchService
from app.services.uuid_path_param import validate_uuid_path

router = APIRouter()

VIEW = "order_management.branches.view"


@router.get("/", response_model=ListResponse[BranchResponse])
def list_branches(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query("last_synced_at"),
    dir: Optional[str] = Query("desc"),
    book: Optional[str] = Query(None),
    in_crm: Optional[bool] = Query(None),
    customer_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The branches, searched on customer code, branch code and branch name."""
    if customer_id:
        validate_uuid_path(customer_id, resource="Customer")
    return BranchService(db).list_branches(
        page=page,
        limit=limit,
        query=query,
        sort_field=sort or "last_synced_at",
        sort_dir=dir or "desc",
        book=book,
        in_crm=in_crm,
        customer_id=customer_id,
    )


@router.get("/books", response_model=List[str])
def list_books(
    current_user: dict = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
):
    """The books present, for the list's Book filter."""
    return BranchService(db).books()
