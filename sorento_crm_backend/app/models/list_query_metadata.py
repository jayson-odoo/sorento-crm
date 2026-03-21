"""DB-driven metadata for dynamic list filters and exports."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str():
    return str(uuid.uuid4())


class ListQueryResource(Base):
    __tablename__ = "list_query_resources"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    resource_key = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    fields = relationship("ListQueryField", back_populates="resource", cascade="all, delete-orphan")


class ListQueryField(Base):
    __tablename__ = "list_query_fields"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    resource_id = Column(
        UUID(as_uuid=False),
        ForeignKey("list_query_resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_key = Column(String(128), nullable=False)
    label = Column(String(255), nullable=False)
    data_type = Column(String(32), nullable=False)
    compile_key = Column(String(128), nullable=False)
    allowed_operators = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    filterable = Column(Boolean, default=True, nullable=False)
    exportable = Column(Boolean, default=True, nullable=False)
    export_column_name = Column(String(128), nullable=True)
    is_line_field = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    resource = relationship("ListQueryResource", back_populates="fields")

    __table_args__ = (UniqueConstraint("resource_id", "field_key", name="uq_list_query_fields_resource_field"),)
