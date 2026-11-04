"""Browser crash reports (CLIENT-ERROR-REPORT).

One row per error that reached a React error boundary in a staff browser
(`app/global-error.tsx`, `app/(protected)/error.tsx`). Before this table the only
record of "The app could not start" was the reader's own console, so nobody could
say why a tab crashed. Written only by `POST /api/v1/system/client-errors`, which
caps every field and rate-limits per user; deleted after 30 days by the daily
`api_call_log_prune` task.
"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ClientErrorReport(Base):
    __tablename__ = "client_error_report"
    __audit_skip__ = "browser crash telemetry, itself a trail; retention is owned by api_call_log_prune"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    # The reporting user. No other identity is stored: no email, no IP.
    user_id = Column(UUID(as_uuid=False), nullable=True)
    # `global` (root boundary, the "could not start" screen) or `protected` (route boundary).
    boundary = Column(String(16), nullable=False)
    error_name = Column(String(128), nullable=True)
    message = Column(Text, nullable=True)
    stack = Column(Text, nullable=True)
    digest = Column(String(64), nullable=True)
    # Path only: query string and fragment are stripped server-side.
    path = Column(String(512), nullable=True)
    build_sha = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    is_chunk_error = Column(Boolean, nullable=False, default=False)
    client_ts = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_client_error_report_created_at", "created_at"),
        Index("ix_client_error_report_user_created_at", "user_id", "created_at"),
    )
