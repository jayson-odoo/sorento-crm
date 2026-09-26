"""User download model: async-generated files (e.g. complaint PDFs) surfaced in
the "My Downloads" drawer.

A download row is created in status 'pending' when a user requests an export, an
RQ task flips it to 'processing' then 'ready' (with a storage key) or 'failed'
(with an error). The drawer polls per-user rows while any are in flight.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class DownloadStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class UserDownload(Base):
    __tablename__ = "user_downloads"
    __audit_skip__ = "download job rows purged at 30 days; download events come in S1"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    # What kind of export this is, e.g. 'complaint_pdf'. Free-form for forward-compat.
    kind = Column(String(50), nullable=False)
    # Optional source pointer so the drawer can deep-link / dedupe.
    source_entity_type = Column(String(50), nullable=True)
    # Polymorphic (no FK) but always a uuid - see migration 300.
    source_entity_id = Column(UUID(as_uuid=False), nullable=True, index=True)
    status = Column(
        SQLEnum(
            DownloadStatus,
            native_enum=False,
            length=20,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DownloadStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    filename = Column(String(255), nullable=True)
    storage_provider = Column(String(10), nullable=True)  # 's3' | 'r2'
    storage_key = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False, index=True)
    ready_at = Column(DateTime(timezone=False), nullable=True)
    # PLAN-low-stock-report S5 (AC-44/AC-45): when a chat turn runs out of budget before
    # the file is ready, the route CLAIMS delivery for the worker by writing the contact
    # here, and the worker claims the push back by stamping `delivered_at`. Two conditional
    # updates on one row, so exactly one of {the turn returns the file, the worker pushes
    # it} can happen. NULL on every download nobody is waiting for over chat.
    deliver_to_contact_id = Column(UUID(as_uuid=False), nullable=True)
    delivered_at = Column(DateTime(timezone=False), nullable=True)
    # AC-36/AC-43: stamped by `generate_low_stock_report` at `mark_ready`, so the chat
    # route can state "Low: 12 of 340 planned products" without opening the workbook on
    # the request thread. NULL for every other kind.
    row_count_low = Column(Integer, nullable=True)
    row_count_all = Column(Integer, nullable=True)
    # Generic counts (PLAN-stock-debt-filters-totals-export-24sep.md, AC-12b): unlike the
    # low stock report's fixed two-sheet shape above, this export's sheet count varies with
    # its own `split` choice (1, or one per supplier/category/pair), so it is not a third
    # named pair - `stock_debt_xlsx` is the first writer, and any later export kind whose
    # count is just "rows" and "sheets" reuses these rather than growing a fourth pair.
    row_count = Column(Integer, nullable=True)
    sheet_count = Column(Integer, nullable=True)
