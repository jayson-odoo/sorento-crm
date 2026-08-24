"""Request telemetry for external + MCP-originated API calls.

Separate from `integration_log` on purpose. That table is a **work queue** - 
`retry_count`, `max_retry_allowed`, `next_retry_at`, and a UUID `business_id`
pointing at the row being synced. Chat ingest already fakes that FK with a random
uuid because it has no business row to point at, which is the tell that it was
being borrowed for telemetry it was never shaped for.

This table has no retry semantics and no business FK. It answers "what called us,
when, how long did it take, and what came back" - for every `/api/v1/external/*`
request, written by middleware so coverage is total by construction rather than
per-endpoint opt-in.
"""
import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ApiCallLog(Base):
    __tablename__ = "api_call_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))

    endpoint = Column(String(512), nullable=False)
    method = Column(String(10), nullable=False)
    # Who called: 'mcp', 'n8n', 'unknown'. Derived from X-Source; today n8n and MCP
    # share one EXTERNAL_API_KEY and are otherwise indistinguishable.
    source = Column(String(32), nullable=False, default="unknown")
    # MCP tool name when source='mcp' (X-Tool-Name), else NULL.
    tool_name = Column(String(128), nullable=True)
    # Resolved principal where one exists (API-key act-as user, or JWT subject).
    actor = Column(String(128), nullable=True)

    status_code = Column(Integer, nullable=True)
    # success | client_error | server_error - derived from status_code so the list
    # can filter on intent without every consumer re-deriving the ranges.
    outcome = Column(String(20), nullable=False, default="success")
    latency_ms = Column(Integer, nullable=True)

    # Joins the server-side span to the MCP client's own elapsed_ms measurement.
    correlation_id = Column(String(64), nullable=True)

    # Truncated + redacted. NULLed by the prune task at 30d; the row itself
    # survives to 180d because the metadata stays useful for trend analysis long
    # after the body does.
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_api_call_log_created_at", "created_at"),
        Index("ix_api_call_log_source_created_at", "source", "created_at"),
        Index("ix_api_call_log_correlation_id", "correlation_id"),
        Index("ix_api_call_log_endpoint", "endpoint"),
    )
