"""Import logs API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.import_log_service import ImportLogService
from app.schemas.import_log import ImportLogResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/import-logs", response_model=ListResponse[ImportLogResponse])
async def list_import_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    entity_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List import logs (optional filter by entity_type)."""
    try:
        service = ImportLogService(db)
        return service.list_import_logs(page=page, limit=limit, entity_type=entity_type)
    except HTTPException:
        raise
    except Exception as exc:
        raise handle_internal_error(str(exc))


@router.get("/import-logs/{log_id}", response_model=ImportLogResponse)
async def get_import_log(
    log_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single import log."""
    try:
        service = ImportLogService(db)
        return service.get_import_log(log_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise handle_internal_error(str(exc))
