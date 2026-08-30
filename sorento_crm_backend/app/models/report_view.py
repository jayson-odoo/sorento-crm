"""A saved report view: the filters, the detail columns and the pivot, under a name.

Personal by default. A holder of `reports.views.publish` can share one, and mark one shared
view the default for everyone - hence the partial unique index: at most one `is_default`
per report key, enforced by the database rather than by whoever remembers to clear the old
one.

The config is JSONB because it is a screen shape, not a queryable entity: nothing joins to
"the columns of a view". It is validated against the report definition on the way in
(`app/schemas/report.py` + the engine), which is where a bad column key is caught.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func, text

from app.database import Base


class ReportView(Base):
    __tablename__ = "report_views"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The registry key of the report this view belongs to (e.g. 'sponsorship').
    report_key = Column(Text, nullable=False, index=True)
    owner_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    # {"params": {...}, "detail": {"columns": [...], "order": [...]},
    #  "pivot": {"rows": ..., "cols": ..., "measures": [...]}}
    view = Column(JSONB, nullable=False)
    is_shared = Column(Boolean, nullable=False, default=False, server_default="false")
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("report_key", "owner_user_id", "name", name="uq_report_views_owner_name"),
        Index(
            "uq_report_views_one_default",
            "report_key",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
