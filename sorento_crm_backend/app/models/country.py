"""Countries master (S1, `PLAN-local-supplier-oi-routing.md`).

A reference table a supplier's Country FK points at today, a customer's and a user's
later - copied off Units of Measure's shape rather than the existing Lookup Sets
mechanism (owner's ruling, 10 Sep 2026): a reference entity with its own FK column,
not a keyword bound to a form field.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


class Country(Base, CompanyScopedMixin):
    __tablename__ = "countries"
    # Migration-seeded, shared vocabulary (249 ISO rows, no company of their own) - the
    # same reason `PromotionType` sets it: without it a scoped user's owned
    # `company_id IN (...)` predicate excludes every NULL-company seed row outright.
    __company_shared__ = True

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(2), nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        # Case-insensitive unique, at the database - `CountryService` also checks this
        # itself (AC-2.5) so a duplicate reads as a 409 rather than a raw IntegrityError.
        Index("uq_countries_code_lower", func.lower(code), unique=True),
    )
