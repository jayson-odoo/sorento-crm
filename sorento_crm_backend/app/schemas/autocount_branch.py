"""Customer Branches list (#1356): the AutoCount branch table, read only."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BranchResponse(BaseModel):
    id: str
    source_book: str
    # AutoCount `AccNo`: the debtor the branch belongs to, `""` when AutoCount sent none.
    acc_no: str
    branch_code: str
    branch_name: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    # The CRM customer whose code matches `acc_no` in the branch's company, if any.
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
