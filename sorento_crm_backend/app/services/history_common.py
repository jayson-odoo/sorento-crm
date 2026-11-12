"""Helpers the History reads share (STANDARD-HISTORY wave 2): the order inquiry History,
the planning (SO) History and the sales order History all merge `audit_logs` rows for the
same two spellings of the OI row entity, window raises the same way and print times the same."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

#: Both spellings: the audit type the writer uses, and the table name older tooling used.
ROW_AUDIT_TYPES = ("project_order_inquiry_rows", "order_inquiry_rows")
#: Rows created this close to a raise or a revision were made by it.
RAISE_WINDOW = timedelta(seconds=5)


def iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None
