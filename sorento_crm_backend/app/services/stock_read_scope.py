"""Stock reads for a spare part requester: quantities, never the documents behind them.

SPARE-PART-ORDER-REQUEST (security re-check C1, browser pass D2). A holder of
`procurement.spare_part_requests.create` sees a line's stock (UAC R3) without holding any grant
that opens sales orders, purchase orders or SPOs. The two stock reads the request's line expand
uses (`/project-sales/fulfilment-planning/stock-detail`, `/inventory/stock-status`) answer such
a caller with the per-location quantities only; this is the one place that strips them.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

SPARE_PART_CREATE = "procurement.spare_part_requests.create"


def quantities_only(
    payload: Mapping[str, Any],
    document_keys: Iterable[str],
    nested: Mapping[str, Iterable[str]] | None = None,
) -> dict:
    """`payload` with every document list emptied: `document_keys` at the top level, and for
    each `nested` list key, those keys on every item of it. Quantities stay as they are."""
    out = dict(payload)
    for key in document_keys:
        if key in out:
            out[key] = []
    for list_key, item_keys in (nested or {}).items():
        item_keys = tuple(item_keys)
        out[list_key] = [
            {**item, **{k: [] for k in item_keys if k in item}} for item in out.get(list_key) or []
        ]
    return out
