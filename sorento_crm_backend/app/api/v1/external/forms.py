"""External API for forms."""
import html
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.forms import Form
from app.models.resources import Attachment
from app.api.v1.external.utils import scope_to_attachment_company
from app.schemas.external.forms import FormCreateRequest, FormCreateResponse
from app.schemas.forms import FormCreate, FormResponse
from app.services.forms_service import FormService
from app.services.attachment_notification_helper import (
    build_form_detail_url,
    notify_after_external_attachment_entity,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=FormCreateResponse)
def create_form(
    payload: FormCreateRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """
    Create a form from external payload. Only form (code, name, description, language, attachment_id) is used;
    form_sections and form_fields are accepted but ignored.
    attachment_id can be sent at the root or inside form; it sets forms.attachment_id so the form shows
    the attachment on the form detail page and the attachment's Forms tab shows this form.
    The attachment must exist. If form code already exists, returns success with already_existed=true
    and message about duplication.
    """
    f = payload.form
    attachment_id = payload.attachment_id if payload.attachment_id is not None else f.attachment_id
    if attachment_id:
        att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if not att:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Attachment not found: {attachment_id}",
            )
        # Multi-company isolation (Group G): pin the scope to the attachment's
        # company so any company-scoped rows created downstream auto-stamp it.
        # Form itself is a shared (cross-company) entity — matched by unique code,
        # never company-scoped — so a NULL-company (shared form) attachment leaves
        # the scope untouched (AC-G3) and this is a defensive no-op for the Form.
        scope_to_attachment_company(db, att)
    # Default external-created forms to active so they show up in the FE list
    # and MCP surfaces without a separate activation step. Caller can pass
    # ``is_active: false`` explicitly to opt out.
    is_active = f.is_active if f.is_active is not None else True
    form_data = FormCreate(
        code=f.code,
        name=f.name,
        purpose=f.description,
        language=(f.language or "en").strip() or "en",
        attachment_id=attachment_id,
        is_active=is_active,
    )

    existing = db.query(Form).filter(Form.code == form_data.code).first()
    if existing:
        db.refresh(existing)
        if attachment_id:
            try:
                code = (existing.code or "").strip() or "—"
                name = (existing.name or "").strip() or code
                summary_plain = (
                    f'Form "{name}" ({code}) was recorded in Sorento CRM.'
                    " The form code already existed."
                )
                summary_html = (
                    f"<p>Form <strong>{html.escape(name)}</strong> (<strong>{html.escape(code)}</strong>) was "
                    "recorded in Sorento CRM. "
                    "The form code already existed.</p>"
                )
                notify_after_external_attachment_entity(
                    db,
                    [attachment_id],
                    payload.notify_user_id,
                    notif_type="external_form_created",
                    title=f"Form: {code}",
                    summary_plain=summary_plain,
                    summary_html=summary_html,
                    entity_url=build_form_detail_url(str(existing.id)),
                    entity_link_text="Open form in Sorento CRM",
                )
            except Exception as e:
                logger.warning("External form notification failed (already_existed): %s", e, exc_info=True)
        return FormCreateResponse(
            form=FormResponse.model_validate(existing),
            already_existed=True,
            message="Form code already exists.",
        )

    service = FormService(db)
    created_by = current_user.get("id") or "system"
    try:
        form = service.create_form(form_data, created_by)
        if attachment_id:
            try:
                code = (form.code or "").strip() or "—"
                name = (form.name or "").strip() or code
                summary_plain = (
                    f'Form "{name}" ({code}) was created in Sorento CRM '
                )
                summary_html = (
                    f"<p>Form <strong>{html.escape(name)}</strong> (<strong>{html.escape(code)}</strong>) was "
                    "created in Sorento CRM.</p>"
                )
                notify_after_external_attachment_entity(
                    db,
                    [attachment_id],
                    payload.notify_user_id,
                    notif_type="external_form_created",
                    title=f"Form created: {code}",
                    summary_plain=summary_plain,
                    summary_html=summary_html,
                    entity_url=build_form_detail_url(str(form.id)),
                    entity_link_text="Open form in Sorento CRM",
                )
            except Exception as e:
                logger.warning("External form notification failed: %s", e, exc_info=True)
        return FormCreateResponse(
            form=FormResponse.model_validate(form),
            already_existed=False,
            message=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
