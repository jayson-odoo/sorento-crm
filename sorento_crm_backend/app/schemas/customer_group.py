"""Customer group schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CustomerGroupWrite(BaseModel):
    """Create / rename body. Blank is refused by the service (422), after trimming."""

    name: str


class CustomerGroupResponse(BaseModel):
    id: str
    name: str
    ledger_count: int = 0
    # Sorted distinct `customers.account_level` of the members; none when no member is numbered.
    account_levels: List[int] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CustomerGroupSelect(BaseModel):
    id: str
    name: str
    ledger_count: int = 0


class CustomerGroupCustomersAssign(BaseModel):
    customer_ids: List[str]
