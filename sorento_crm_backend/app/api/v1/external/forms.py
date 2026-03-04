"""External API for forms."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.forms import Form
from app.schemas.external import FormCreateRequest, FormCreateResponse
from app.schemas.forms import FormCreate, FormResponse
from app.services.forms_service import FormService

router = APIRouter()


@router.post("/", response_model=FormCreateResponse)
def create_form(
    payload: FormCreateRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create a form from external payload. Only form (code, name, description, language, attachment_id) is used;
    form_sections and form_fields are accepted but ignored.
    When attachment_id is provided, the form is linked to that attachment (forms.attachment_id);
    the attachment must exist. If form code already exists, returns success with already_existed=true
    and message about duplication.
    """
    f = payload.form
    form_data = FormCreate(
        code=f.code,
        name=f.name,
        purpose=f.description,
        language=(f.language or "en").strip() or "en",
        attachment_id=f.attachment_id,
    )

    existing = db.query(Form).filter(Form.code == form_data.code).first()
    if existing:
        db.refresh(existing)
        return FormCreateResponse(
            form=FormResponse.model_validate(existing),
            already_existed=True,
            message="Form code already exists.",
        )

    service = FormService(db)
    created_by = current_user.get("id") or "system"
    try:
        form = service.create_form(form_data, created_by)
        return FormCreateResponse(
            form=FormResponse.model_validate(form),
            already_existed=False,
            message=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
