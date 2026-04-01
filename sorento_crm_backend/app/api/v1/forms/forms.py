"""Forms API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.services.forms_service import FormService
from app.schemas.forms import (
    FormCreate,
    FormUpdate,
    FormResponse,
    FormSubmissionCreate,
    FormSubmissionUpdate,
    FormSubmissionResponse,
)
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error


class BulkDeleteFormsRequest(BaseModel):
    ids: list[str]

router = APIRouter()


@router.get("/", response_model=ListResponse[FormResponse])
async def get_forms(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get forms with pagination and filtering."""
    try:
        service = FormService(db)
        # Handle empty strings or None values
        sort_field = (sort and sort.strip()) or "updated_at"
        sort_dir = (dir and dir.strip()) or "desc"
        result = service.list_forms(
            page=page, 
            limit=limit, 
            query=query, 
            language=language, 
            status=status,
            sort_field=sort_field,
            sort_dir=sort_dir
        )
        return result
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_forms: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/{form_id}", response_model=FormResponse)
async def get_form(
    form_id: str,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single form by ID."""
    try:
        service = FormService(db)
        form = service.get_form(form_id)
        return form
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=FormResponse, status_code=status.HTTP_201_CREATED)
async def create_form(
    form_data: FormCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new form."""
    try:
        service = FormService(db)
        form = service.create_form(form_data, current_user["id"])
        return form
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{form_id}", response_model=FormResponse)
async def update_form(
    form_id: str,
    form_data: FormUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a form."""
    try:
        service = FormService(db)
        form = service.update_form(form_id, form_data)
        return form
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_forms(
    body: BulkDeleteFormsRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk delete forms by ID."""
    try:
        service = FormService(db)
        return service.bulk_delete_forms(body.ids)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{form_id}", status_code=status.HTTP_200_OK)
async def delete_form(
    form_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a form (cascades to sections, fields, versions, submissions)."""
    try:
        service = FormService(db)
        return service.delete_form(form_id)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/submissions", response_model=FormSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_form_submission(
    submission_data: FormSubmissionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a form submission."""
    try:
        service = FormService(db)
        submission = service.create_submission(submission_data, current_user["id"])
        return submission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/submissions/{submission_id}", response_model=FormSubmissionResponse)
async def update_form_submission(
    submission_id: str,
    submission_data: FormSubmissionUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a form submission."""
    try:
        service = FormService(db)
        submission = service.update_submission(submission_id, submission_data)
        return submission
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
