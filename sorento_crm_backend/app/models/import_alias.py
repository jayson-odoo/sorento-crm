"""Import column aliases: how a spreadsheet header maps to a canonical field.

Every importer in this codebase resolves columns with a hardcoded candidate tuple -
``_find(row, "grn_number", "grn no", ...)``. That works for one client and makes the next
client a code change, which is the thing that stops this module being reusable.

So the candidates live in a table instead. A canonical field has many aliases, each
optionally tagged with a locale, because real files arrive with both English and Chinese
headers in the same workbook. Onboarding a client with different export headers becomes
INSERTs plus a re-run, and a failed import is diagnosable on a screen rather than in a
database session.

Deliberately NOT company-scoped: header conventions belong to the tenant's source system,
not to one of its operating companies.
"""
import uuid

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class ImportFieldAlias(Base):
    __tablename__ = "import_field_alias"

    # `server_default` as well as `default`: migration 311 creates this column with
    # gen_random_uuid(), and the seeder inserts by raw SQL. A Python-side default alone
    # covers ORM inserts only, so a create_all schema would reject the seed while a migrated
    # one accepts it.
    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        server_default=text("gen_random_uuid()"),
    )
    # Which kind of document this alias applies to, e.g. outstanding_so, packing_list.
    doc_type = Column(String(64), nullable=False)
    # The canonical field name the importer asks for, e.g. item_code, required_date.
    field = Column(String(64), nullable=False)
    # The header text as it actually appears in a file, e.g. "ITEM CODE" or "型号".
    alias = Column(String(255), nullable=False)
    # Advisory only: resolution never filters on locale, it is there so a human editing
    # the table can see why two aliases exist for one field.
    locale = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("doc_type", "field", "alias", name="uq_import_field_alias_triple"),
        Index("ix_import_field_alias_doc_type_field", "doc_type", "field"),
    )
