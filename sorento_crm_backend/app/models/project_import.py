"""Saved value links for the project import (lane PROJECT-MIGRATION-TOOL).

`PLAN-project-import-12nov.md` ("Model and migration"). One row is one choice a person made
for one folded value of the PO register workbook: the customer text `CUSTOMER 001 SDN BHD`
links to a customer, the (customer, project name) pair is created as a new project, and so
on. A later file with the same folded value is prefilled from here, so only new values need
a person. Nothing is ever saved here without a person picking it.

The run itself is an `import_jobs` row (`job_type = project_po_register`); this is the only
new table.
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin

KIND_CUSTOMER = "customer"
KIND_PROJECT = "project"
KIND_DEVELOPER = "developer"
KIND_PERSON = "person"
KINDS = (KIND_CUSTOMER, KIND_PROJECT, KIND_DEVELOPER, KIND_PERSON)

ACTION_LINK = "link"
ACTION_CREATE = "create"
ACTION_SKIP = "skip"
ACTION_NONE = "none"


def _uuid_str() -> str:
    return str(uuid.uuid4())


class ProjectImportValueMap(Base, CompanyScopedMixin):
    __tablename__ = "import_value_maps"
    # Born straight into `projects`: the `project_` audit prefix its siblings pin (ADR-0011).
    __audit_entity_type__ = "project_import_value_maps"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    kind = Column(String(16), nullable=False)
    #: The folded customer of a project pair; '' for every other kind, so the unique key
    #: holds no NULL.
    customer_value_key = Column(String(255), nullable=False, default="", server_default=text("''"))
    #: The folded value: trimmed, inner whitespace collapsed, upper-cased. Nothing else.
    value_key = Column(String(255), nullable=False)
    #: The value as first seen in a file.
    value_text = Column(Text, nullable=True)
    action = Column(String(8), nullable=False)
    target_id = Column(String(64), nullable=True)
    new_title = Column(Text, nullable=True)
    set_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    set_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_import_value_maps_key",
            "company_id",
            "kind",
            "customer_value_key",
            "value_key",
            unique=True,
        ),
        {"schema": "projects"},
    )
