"""SORENTO-TOWN: one frozen row per company per day (`town_days`).

The live town is served from Redis; this row is what the first tick at or after 22:00 MYT
leaves behind: the day's final snapshot plus the day's posted documents in creation order
(`events`, for the phase 2 replay). Plan: documentation/plans/dashboard/PLAN-sorento-town-08nov.md.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


class TownDay(Base, CompanyScopedMixin):
    __tablename__ = "town_days"
    __table_args__ = (UniqueConstraint("company_id", "day", name="uq_town_days_company_day"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    day = Column(Date, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    events = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
