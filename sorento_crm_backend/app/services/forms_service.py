"""Forms service for business logic."""
from sqlalchemy.orm import Session
from typing import Optional
from app.models.forms import Form, FormSection, FormField, FormVersion
from app.models.resources import Attachment
from app.schemas.forms import (
    FormCreate, FormUpdate, FormSectionCreate, FormSectionUpdate,
    FormFieldCreate, FormFieldUpdate, FormVersionCreate
)
from app.services.error_handler import handle_not_found, handle_conflict


class FormService:
    """Service for form operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_forms(self, page: int = 1, limit: int = 50, query: Optional[str] = None, language: Optional[str] = None, status: Optional[str] = None, sort_field: str = "updated_at", sort_dir: str = "desc"):
        """List forms."""
        from sqlalchemy import or_, and_
        from sqlalchemy.orm import joinedload
        q = self.db.query(Form).options(
            joinedload(Form.attachment).joinedload(Attachment.attachment_type)
        )
        
        filters = []
        if query:
            filters.append(
                or_(
                    Form.code.ilike(f"%{query}%"),
                    Form.name.ilike(f"%{query}%")
                )
            )
        if language:
            filters.append(Form.language == language)
        if status and status != "all":
            filters.append(Form.is_active == (status == "active"))
        
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
            "created_at": Form.created_at,
            "updated_at": Form.updated_at,
            "version": Form.version,
        }
        sort_column = sort_map.get(sort_field, Form.updated_at)
        
        # Ensure sort_dir is either "asc" or "desc"
        if sort_dir not in ["asc", "desc"]:
            sort_dir = "desc"
        
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        forms = q.offset(offset).limit(limit).all()
        
        from app.schemas.common import PaginationResponse
        
        return {
            "data": forms,
            "pagination": PaginationResponse(total=total, page=page, limit=limit),
            "empty": total == 0
        }
    
    def get_form(self, form_id: str):
        """Get a form by ID."""
        from sqlalchemy.orm import joinedload
        form = self.db.query(Form).options(
            joinedload(Form.attachment).joinedload(Attachment.attachment_type)
        ).filter(Form.id == form_id).first()
        if not form:
            raise handle_not_found("Form", form_id)
        return form
    
    def create_form(self, form_data: FormCreate, created_by: str):
        """Create a new form."""
        existing = self.db.query(Form).filter(Form.code == form_data.code).first()
        if existing:
            raise handle_conflict("Form code already exists.")
        
        form_dict = form_data.model_dump()
        # created_by column doesn't exist in database, skip setting it
        # form_dict["created_by"] = created_by
        form = Form(**form_dict)
        self.db.add(form)
        self.db.commit()
        self.db.refresh(form)
        return form
    
    def update_form(self, form_id: str, form_data: FormUpdate):
        """Update a form."""
        form = self.get_form(form_id)
        
        update_data = form_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(form, key, value)
        
        self.db.commit()
        self.db.refresh(form)
        return form


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
