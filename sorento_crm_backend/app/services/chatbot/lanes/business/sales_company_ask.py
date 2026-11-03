"""The contact's own companies, as the sales lanes read them (SALES-COMPANY item 1).

The sales analysis's company question ("Sorento or Mocha?", AC-S1-21) was asked here through the shared
`required_fields` slot. Owner O-R2 (3 Nov 2026) removed it: an ask naming no company runs over every company the
contact holds, and the report ask's reply shows each one's total. What stays is the contact's companies in the
question's old order (`_companies`, read by the report ask lane), and the slot name a live session may still hold.
"""
from __future__ import annotations

from typing import Any

ASK_NAME = "sales_company"


def _companies(db: Any, contact_id: Any, space_id: Any) -> list[tuple[str, str, str]]:
    from app.api.v1.sales.analysis import contact_companies
    from app.services.field_access import resolve_contact_with_null_workspace_fallback

    if db is None or not contact_id or not str(contact_id).strip():
        return []
    resolved = resolve_contact_with_null_workspace_fallback(
        db, contact_id=str(contact_id).strip(), space_id=(str(space_id).strip() or None) if space_id else None
    )
    return contact_companies(db, str(resolved)) if resolved else []
