"""A saved view of a listing: its filters, sort and column layout, under a name.

Generalised from `report_views` (`app/models/report_view.py`) for S4 of
PLAN-scm-reorder-oi-feedback-1sep.md: any DataGrid listing can have segments the same
way a report can have saved views, keyed by the SAME `listing_key` the column-config
personalization endpoints already use (`app/api/v1/list_query.py:_can_view_listing_key`).

Personal by default. A holder of `list_query.saved_views.publish` can share one, and mark
one shared view the default for everyone within a listing key - hence the partial unique
index: at most one `is_default` per listing key, enforced by the database rather than by
whoever remembers to clear the old one.

The config is JSONB because it is a screen shape, not a queryable entity: nothing joins
to "the filters of a view". Unlike `report_views`, nothing here validates it against a
catalog on the way in - the field descriptor a saved view's filters were built from lives
on the FRONTEND (`components/list/DynamicFilterBuilder.tsx`), beside the listing's own
column defs, so the backend never has an opinion on what a valid filter looks like.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func, text

from app.database import Base


class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # e.g. "scm.dashboard.view::reorder-plan-lines" - the same key the DataGrid's own
    # column-config personalization is stored under.
    listing_key = Column(Text, nullable=False, index=True)
    owner_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    # {"filters": ListQueryFilterGroup | null, "sort": [{"id", "desc"}],
    #  "columns": [...visible column ids...], "column_order": [...]}
    view = Column(JSONB, nullable=False)
    is_shared = Column(Boolean, nullable=False, default=False, server_default="false")
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("listing_key", "owner_user_id", "name", name="uq_saved_views_owner_name"),
        Index(
            "uq_saved_views_one_default",
            "listing_key",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
