"""UI v2 page-view telemetry (UI-V2 phase 0, D10).

One row per route change recorded by the v2 shell hook. Written only by
`POST /api/v1/system/page-views`, which stores a route PATTERN (a segment holding a digit becomes `[id]`; no query),
caps the batch and rate-limits per user; deleted after 90 days by the daily
`api_call_log_prune` task.
"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UiPageView(Base):
    __tablename__ = "ui_page_views"
    __audit_skip__ = "page-view telemetry, itself a trail; retention is owned by api_call_log_prune"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    route = Column(String(200), nullable=False)
    viewport = Column(String(8), nullable=False)
    ui_version = Column(String(2), nullable=False)
    ms_to_first_data = Column(Integer, nullable=True)
    viewed_at = Column(DateTime(timezone=False), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_ui_page_views_created_at", "created_at"),
        Index("ix_ui_page_views_user_created_at", "user_id", "created_at"),
    )
