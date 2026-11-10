"""B12 (AC-E2E-DB3, 10 Nov 2026): which PO rows a Stock Debt link is replacing right now.

SS write API v2 (SS #230) makes a PO link, change link or unlink a REPLACE: AutoCount gives the
row a new DtlKey (and a new Seq), and SS pushes the read-back to the PO ingest DURING the call,
before the CRM sees `replacedLines`. Without help the ingest reads that as one line removed (OI
links released, "removed in AutoCount") and one created. Before each send the link service
records the row it is replacing; the ingest pairs that vanished row with the ONE incoming row of
the same product, qty and SO link, so the CRM line (same id) is re-keyed instead.

Kept in the same Redis as the attempt count (no schema), for a few minutes. With Redis down
nothing is recorded and `StockDebtPoLinkService._apply` merges the ingest's duplicate instead.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from app.services import autocount_idempotency as idem

logger = logging.getLogger(__name__)

_PREFIX = "sorento:autocount_write:po_replace:"
# Long enough for a slow SS call plus its ingest push; a stale hint can only pair a vanished
# row with an identical one (same product, qty and SO link), which is the same row anyway.
_TTL_SECONDS = 15 * 60


def _qty(value: Any) -> str:
    return format(Decimal(str(value or 0)).normalize(), "f")


def _so(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


def remember(old_ref: str, *, qty: Any, from_so_ref: Optional[str]) -> None:
    """The row `old_ref` is about to be replaced by a row of `qty` linked to `from_so_ref`."""
    store = idem.attempt_store()
    if store is None:
        return
    try:
        store.set(f"{_PREFIX}{old_ref.strip()}",
                  json.dumps({"qty": _qty(qty), "so": _so(from_so_ref)}), ex=_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("po link: could not record the replace hint")
        idem._store_failed()


def lookup(refs: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """`{old_ref: {"qty": str, "so": ref or None}}` for the refs that have a live hint."""
    store = idem.attempt_store()
    if store is None:
        return {}
    found: Dict[str, Dict[str, Any]] = {}
    try:
        for ref in refs:
            raw = store.get(f"{_PREFIX}{ref.strip()}")
            if raw:
                found[ref] = json.loads(raw)
    except Exception:  # noqa: BLE001
        logger.warning("po ingest: replace hints unreachable, no pairing")
        idem._store_failed()
        return {}
    return found


def matches(hint: Dict[str, Any], values: Dict[str, Any]) -> bool:
    return hint.get("qty") == _qty(values.get("qty_ordered")) and hint.get("so") == _so(
        values.get("from_so_line_ref")
    )
