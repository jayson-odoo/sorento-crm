"""Forms service for business logic."""
from sqlalchemy.orm import Session
from typing import Optional
from app.models.forms import Form, FormSection, FormField, FormVersion, FormSubmission
from app.models.resources import Attachment
from app.schemas.forms import (
    FormCreate, FormUpdate, FormSectionCreate, FormSectionUpdate,
    FormFieldCreate, FormFieldUpdate, FormVersionCreate,
    FormSubmissionCreate, FormSubmissionUpdate
)
from app.services.error_handler import handle_not_found, handle_conflict
from app.services.embedding_events import publish_embedding_event


class FormService:
    """Service for form operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def _build_list_query(
        self,
        query: Optional[str] = None,
        language: Optional[str] = None,
        status: Optional[str] = None,
        form_type: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
        sort_field: str = "updated_at",
        sort_dir: str = "desc",
        entity_form_codes: Optional[list[str]] = None,
        form_ids: Optional[list[str]] = None,
        with_options: bool = True,
    ):
        """Build the filtered + sorted forms query shared by ``list_forms`` and
        ``neighbours`` so the two can never drift.

        The ORDER BY always appends ``Form.id`` as a deterministic tie-breaker so
        offset position and prev/next neighbours are unambiguous when the primary
        sort column has equal values. ``with_options`` controls whether the
        attachment eager-load is applied (skipped for the ids-only neighbours scan).
        """
        from sqlalchemy import or_, and_, cast, String, text, func
        from sqlalchemy.dialects.postgresql import ARRAY
        from sqlalchemy.orm import joinedload
        q = self.db.query(Form)
        if with_options:
            q = q.options(
                joinedload(Form.attachment).joinedload(Attachment.attachment_type)
            )

        filters = []
        if form_type and str(form_type).strip().lower() not in ("", "all"):
            from sqlalchemy import func as _f
            ft = str(form_type).strip().lower()
            # Normalize common agent aliases: "marketing_form" → "marketing",
            # "marketing form" → "marketing", "marketing-form" → "marketing".
            for suffix in ("_form", " form", "-form", "_forms", " forms"):
                if ft.endswith(suffix):
                    ft = ft[: -len(suffix)]
                    break
            filters.append(_f.lower(Form.form_type) == ft)
        if entity_form_codes:
            lowered = [c.lower() for c in entity_form_codes if c]
            filters.append(func.lower(Form.code).in_(lowered))
        if form_ids:
            filters.append(Form.id.in_(form_ids))
        if query:
            ql = query.strip()
            q = q.outerjoin(Attachment, Form.attachment_id == Attachment.id)
            filters.append(
                or_(
                    Form.code.ilike(f"%{ql}%"),
                    Form.name.ilike(f"%{ql}%"),
                    Form.purpose.ilike(f"%{ql}%"),
                    Form.form_type.ilike(f"%{ql}%"),
                    Attachment.original_filename.ilike(f"%{ql}%"),
                    Attachment.stored_filename.ilike(f"%{ql}%"),
                )
            )
        if language:
            filters.append(Form.language == language)
        if status and status != "all":
            filters.append(Form.is_active == (status == "active"))
        if contact_access_codes is not None:
            if not contact_access_codes:
                filters.append(text("false"))
            else:
                filters.append(
                    Form.access_levels.op("?|")(
                        cast(contact_access_codes, ARRAY(String))
                    )
                )

        if filters:
            q = q.filter(and_(*filters))

        # Normalize sort parameters
        if sort_field and isinstance(sort_field, str):
            sort_field = sort_field.strip().lower() or "updated_at"
        else:
            sort_field = "updated_at"

        if sort_dir and isinstance(sort_dir, str):
            sort_dir = sort_dir.strip().lower() or "desc"
        else:
            sort_dir = "desc"

        sort_map = {
            "id": Form.id,
            "code": Form.code,
            "name": Form.name,
            "form_type": Form.form_type,
            "created_at": Form.created_at,
            "updated_at": Form.updated_at,
            "version": Form.version,
        }
        sort_column = sort_map.get(sort_field, Form.updated_at)

        # Ensure sort_dir is either "asc" or "desc"
        if sort_dir not in ["asc", "desc"]:
            sort_dir = "desc"

        # Append Form.id as a deterministic tie-breaker so neighbour ordering is
        # stable when the primary sort column has equal values.
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc(), Form.id.asc())
        else:
            q = q.order_by(sort_column.asc(), Form.id.asc())
        return q

    def neighbours(
        self,
        form_id: str,
        query: Optional[str] = None,
        language: Optional[str] = None,
        status: Optional[str] = None,
        form_type: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
        sort_field: str = "updated_at",
        sort_dir: str = "desc",
        entity_form_codes: Optional[list[str]] = None,
        form_ids: Optional[list[str]] = None,
    ) -> dict:
        """Resolve prev/next neighbours for ``form_id`` within the active list query.

        Selects only the ordered ids (not full rows) for efficiency, then defers the
        position/wrap math to the pure ``compute_neighbours`` helper. If the record is
        not in the filtered set (deep link, or filtered out after an edit), falls back
        to the unfiltered, default-sorted set so the pager is never dead (D2).
        """
        from app.services.record_navigation import compute_neighbours

        def _ordered_ids(q) -> list[str]:
            return [str(row[0]) for row in q.with_entities(Form.id).all()]

        filtered_q = self._build_list_query(
            query=query,
            language=language,
            status=status,
            form_type=form_type,
            contact_access_codes=contact_access_codes,
            sort_field=sort_field,
            sort_dir=sort_dir,
            entity_form_codes=entity_form_codes,
            form_ids=form_ids,
            with_options=False,
        )
        result = compute_neighbours(_ordered_ids(filtered_q), form_id)
        if result["index"] is not None:
            return result

        # D2: current record not in the filtered set -> fall back to the unfiltered,
        # default-sorted set so prev/next still works and total reflects all forms.
        unfiltered_q = self._build_list_query(with_options=False)
        return compute_neighbours(_ordered_ids(unfiltered_q), form_id)

    def list_forms(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        language: Optional[str] = None,
        status: Optional[str] = None,
        form_type: Optional[str] = None,
        contact_access_codes: Optional[list[str]] = None,
        sort_field: str = "updated_at",
        sort_dir: str = "desc",
        entity_form_codes: Optional[list[str]] = None,
        form_ids: Optional[list[str]] = None,
    ):
        """List forms."""
        q = self._build_list_query(
            query=query,
            language=language,
            status=status,
            form_type=form_type,
            contact_access_codes=contact_access_codes,
            sort_field=sort_field,
            sort_dir=sort_dir,
            entity_form_codes=entity_form_codes,
            form_ids=form_ids,
        )

        total = q.count()
        offset = (page - 1) * limit
        forms = q.offset(offset).limit(limit).all()
        
        from app.schemas.common import PaginationResponse
        
        return {
            "data": forms,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_form(self, form_id: str, contact_access_codes: Optional[list[str]] = None):
        """Get a form by ID."""
        from sqlalchemy import cast, String, text
        from sqlalchemy.dialects.postgresql import ARRAY
        from sqlalchemy.orm import joinedload
        q = self.db.query(Form).options(
            joinedload(Form.attachment).joinedload(Attachment.attachment_type)
        ).filter(Form.id == form_id)
        if contact_access_codes is not None:
            if not contact_access_codes:
                q = q.filter(text("false"))
            else:
                q = q.filter(
                    Form.access_levels.op("?|")(
                        cast(contact_access_codes, ARRAY(String))
                    )
                )
        form = q.first()
        if not form:
            raise handle_not_found("Form", form_id)
        return form
    
    def create_form(self, form_data: FormCreate, created_by: str):
        """Create a new form."""
        existing = self.db.query(Form).filter(Form.code == form_data.code).first()
        if existing:
            raise handle_conflict("Form code already exists.")
        
        from app.services.contact_access_type_service import ContactAccessTypeService

        form_dict = form_data.model_dump()
        access_svc = ContactAccessTypeService(self.db)
        if form_dict.get("access_levels"):
            form_dict["access_levels"] = access_svc.validate_access_levels(
                form_dict["access_levels"], field_name="access_levels"
            )
        else:
            form_dict["access_levels"] = access_svc.get_default_access_levels()
        # created_by column doesn't exist in database, skip setting it
        # form_dict["created_by"] = created_by
        form = Form(**form_dict)
        self.db.add(form)
        self.db.commit()
        self.db.refresh(form)
        publish_embedding_event(
            self.db,
            source_type="form",
            source_id=form.id,
            source_key=form.code,
            source_updated_at=form.updated_at or form.created_at,
            event_type="form.created",
            changed_fields=["code", "name", "form_type", "purpose", "language", "is_active"],
            triggered_by=created_by,
        )
        return form
    
    def update_form(self, form_id: str, form_data: FormUpdate):
        """Update a form."""
        form = self.get_form(form_id)
        
        update_data = form_data.model_dump(exclude_unset=True)
        if "access_levels" in update_data and update_data["access_levels"]:
            from app.services.contact_access_type_service import ContactAccessTypeService
            update_data["access_levels"] = ContactAccessTypeService(self.db).validate_access_levels(
                update_data["access_levels"], field_name="access_levels"
            )
        for key, value in update_data.items():
            setattr(form, key, value)
        
        self.db.commit()
        self.db.refresh(form)
        publish_embedding_event(
            self.db,
            source_type="form",
            source_id=form.id,
            source_key=form.code,
            source_updated_at=form.updated_at or form.created_at,
            event_type="form.updated",
            changed_fields=list(update_data.keys()),
        )
        return form

    def delete_form(self, form_id: str) -> dict:
        """Delete a form by ID. Cascades to sections, fields, versions, submissions."""
        form = self.get_form(form_id)
        self.db.delete(form)
        self.db.commit()
        return {"message": "Form deleted successfully"}

    def bulk_delete_forms(self, form_ids: list[str]) -> dict:
        """Delete multiple forms by ID. Returns deleted_count and any not_found ids."""
        if not form_ids:
            return {"message": "No forms to delete", "deleted_count": 0}
        deleted = 0
        for fid in form_ids:
            form = self.db.query(Form).filter(Form.id == fid).first()
            if form:
                self.db.delete(form)
                deleted += 1
        self.db.commit()
        return {"message": f"{deleted} form(s) deleted", "deleted_count": deleted}

    def create_submission(self, submission_data: FormSubmissionCreate, created_by: Optional[str] = None):
        """Create a form submission."""
        submission_dict = submission_data.model_dump()
        submission_dict["created_by"] = created_by
        submission = FormSubmission(**submission_dict)
        self.db.add(submission)
        self.db.commit()
        self.db.refresh(submission)
        return submission

    def update_submission(self, submission_id: str, submission_data: FormSubmissionUpdate):
        """Update a form submission."""
        submission = self.db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
        if not submission:
            raise handle_not_found("Form Submission", submission_id)

        update_data = submission_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(submission, key, value)

        self.db.commit()
        self.db.refresh(submission)
        return submission


class FormSectionService:
    """Service for form section operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_sections(self, form_id: str):
        """List sections for a form."""
        sections = self.db.query(FormSection).filter(
            FormSection.form_id == form_id
        ).order_by(FormSection.section_order).all()
        return sections
    
    def get_section(self, section_id: str):
        """Get a section by ID."""
        section = self.db.query(FormSection).filter(FormSection.id == section_id).first()
        if not section:
            raise handle_not_found("Form Section", section_id)
        return section
    
    def create_section(self, section_data: FormSectionCreate):
        """Create a new section."""
        section = FormSection(**section_data.model_dump())
        self.db.add(section)
        self.db.commit()
        self.db.refresh(section)
        return section
    
    def update_section(self, section_id: str, section_data: FormSectionUpdate):
        """Update a section."""
        section = self.get_section(section_id)
        
        update_data = section_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(section, key, value)
        
        self.db.commit()
        self.db.refresh(section)
        return section


class FormFieldService:
    """Service for form field operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_fields(self, section_id: str):
        """List fields for a section."""
        fields = self.db.query(FormField).filter(
            FormField.section_id == section_id
        ).order_by(FormField.field_order).all()
        return fields
    
    def get_field(self, field_id: str):
        """Get a field by ID."""
        field = self.db.query(FormField).filter(FormField.id == field_id).first()
        if not field:
            raise handle_not_found("Form Field", field_id)
        return field
    
    def create_field(self, field_data: FormFieldCreate):
        """Create a new field."""
        field = FormField(**field_data.model_dump())
        self.db.add(field)
        self.db.commit()
        self.db.refresh(field)
        return field
    
    def update_field(self, field_id: str, field_data: FormFieldUpdate):
        """Update a field."""
        field = self.get_field(field_id)
        
        update_data = field_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(field, key, value)
        
        self.db.commit()
        self.db.refresh(field)
        return field


class FormVersionService:
    """Service for form version operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_versions(self, form_id: str):
        """List versions for a form."""
        versions = self.db.query(FormVersion).filter(
            FormVersion.form_id == form_id
        ).order_by(FormVersion.version_number.desc()).all()
        return versions
    
    def get_version(self, version_id: str):
        """Get a version by ID."""
        version = self.db.query(FormVersion).filter(FormVersion.id == version_id).first()
        if not version:
            raise handle_not_found("Form Version", version_id)
        return version
    
    def create_version(self, version_data: FormVersionCreate, created_by: str):
        """Create a new version."""
        # Check unique constraint
        existing = self.db.query(FormVersion).filter(
            FormVersion.form_id == version_data.form_id,
            FormVersion.version_number == version_data.version_number
        ).first()
        if existing:
            raise handle_conflict("Version number already exists for this form.")
        
        version_dict = version_data.model_dump()
        version_dict["created_by"] = created_by
        version = FormVersion(**version_dict)
        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        return version
