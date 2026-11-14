"""Stock Debt's door onto the shared PO link function (`po_link_service`).

Plan: `documentation/plans/scm/PLAN-oi-po-link-11nov.md`. The logic moved to `PoLinkService`,
which both Stock Debt and Order Inquiries drive through a `PoLinkScope`. This module keeps the
(snapshot, row) call shape the Stock Debt routes and tests use, and re-exports the names they
import.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.autocount_idempotency import attempt_store  # noqa: F401  (tests patch it here)
from app.services.scm.po_link_service import (  # noqa: F401
    ACTIONS,
    SWITCHED_OFF,
    UNREACHABLE,
    WAITING,
    PoLinkScope,
    PoLinkService,
    _INGEST_OWNED,
    _keys,
    _line_numbers,
    _num,
    po_links_for,
    scope_for_snapshot_row,
)


class StockDebtPoLinkService(PoLinkService):
    def __init__(self, db: Session, actor: Optional[dict] = None):
        super().__init__(db, None, actor)

    def _store(self):
        # Looked up here, so a test patching this module's `attempt_store` still takes effect.
        return attempt_store()

    def _for(self, snapshot_id: str, row_id: str) -> "StockDebtPoLinkService":
        self.scope = scope_for_snapshot_row(self.db, snapshot_id, row_id)
        return self

    def options(self, snapshot_id: str, row_id: str) -> Dict[str, Any]:  # type: ignore[override]
        return PoLinkService.options(self._for(snapshot_id, row_id))

    def link(self, snapshot_id: str, row_id: str, lines: List[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
        return PoLinkService.link(self._for(snapshot_id, row_id), lines)

    def unlink(self, snapshot_id: str, row_id: str, po_line_ids: List[str]) -> Dict[str, Any]:  # type: ignore[override]
        return PoLinkService.unlink(self._for(snapshot_id, row_id), po_line_ids)

    def change(self, snapshot_id: str, row_id: str, changes: List[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
        return PoLinkService.change(self._for(snapshot_id, row_id), changes)

    def relink(self, snapshot_id: str, row_id: str, moves: List[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
        return PoLinkService.relink(self._for(snapshot_id, row_id), moves)
