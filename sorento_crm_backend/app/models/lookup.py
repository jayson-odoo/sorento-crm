"""Generic dropdown master-data models. See docs/superpowers/specs/2026-04-30-lookup-sets-design.md."""
import uuid
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, ForeignKey, DateTime, Index, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class LookupSet(Base):
    __tablename__ = "lookup_sets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID(as_uuid=False), nullable=True)
    set_key = Column(String(80), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    options = relationship("LookupOption", back_populates="set", cascade="all, delete-orphan", passive_deletes=True)
    bindings = relationship("LookupBinding", back_populates="set", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "set_key", name="uq_lookup_sets_tenant_setkey"),
        Index("ix_lookup_sets_is_active", "is_active"),
    )


class LookupOption(Base):
    __tablename__ = "lookup_options"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    set_id = Column(UUID(as_uuid=False), ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False)
    value = Column(String(150), nullable=False)
    label = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    set = relationship("LookupSet", back_populates="options")
    keywords = relationship("LookupOptionKeyword", back_populates="option", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        Index("uq_lookup_options_set_value_lower", "set_id", text("lower(value)"), unique=True),
        Index("ix_lookup_options_set_sort", "set_id", "sort_order"),
    )


class LookupOptionKeyword(Base):
    __tablename__ = "lookup_option_keywords"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    option_id = Column(UUID(as_uuid=False), ForeignKey("lookup_options.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(150), nullable=False)
    locale = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    option = relationship("LookupOption", back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("option_id", "keyword", "locale", name="uq_lookup_keywords_unique"),
        Index("ix_lookup_keywords_lower", text("lower(keyword)")),
    )


class LookupBinding(Base):
    __tablename__ = "lookup_bindings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID(as_uuid=False), nullable=True)
    set_id = Column(UUID(as_uuid=False), ForeignKey("lookup_sets.id", ondelete="CASCADE"), nullable=False)
    table_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=False)
    # Optional default option value the FE pre-selects on a NEW form (never overrides
    # an existing value on edit). Validated app-side to be an active option of the set.
    default_value = Column(String(150), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    set = relationship("LookupSet", back_populates="bindings")

    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", "column_name", name="uq_lookup_bindings_tenant_col"),
        Index("ix_lookup_bindings_set", "set_id"),
    )
