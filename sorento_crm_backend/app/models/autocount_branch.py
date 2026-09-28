"""AutoCount branch table, the CRM's own copy (#1354 S2, ruling Q2).

Fed by `POST /external/ingest/branches` from the vendor's `branchbypage` endpoint. A branch is
a debtor's delivery branch in AutoCount, so it is keyed by the book, the debtor account
(`AccNo`, empty when the vendor does not send it) and `BranchCode`. The delivery order ingest
reads it to store the branch name on `orders.branch_name`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base
from app.models.base import CompanyScopedMixin


class Branch(Base, CompanyScopedMixin):
    __tablename__ = "branches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_book = Column(String(20), nullable=False)
    acc_no = Column(String(100), nullable=False, default="", server_default="")
    branch_code = Column(String(100), nullable=False)
    branch_name = Column(String(255), nullable=True)
    source_record = Column(JSONB, nullable=True)
    last_synced_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_branches_company_book_acc_code",
            "company_id", "source_book", "acc_no", "branch_code",
            unique=True,
        ),
    )
