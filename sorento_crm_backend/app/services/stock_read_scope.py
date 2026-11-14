"""Stock reads for a spare part requester: quantities, never the documents behind them.

SPARE-PART-ORDER-REQUEST (security re-check C1, browser pass D2). A holder of
`procurement.spare_part_requests.create` or `.view` sees a line's stock (UAC R3) without holding any grant
that opens sales orders, purchase orders or SPOs. The two stock reads the request's line expand
uses (`/project-sales/fulfilment-planning/stock-detail`, `/inventory/stock-status`) answer such
a caller with the per-location quantities only; this is the one place that strips them.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

SPARE_PART_CREATE = "procurement.spare_part_requests.create"
#: The approver / purchasing read (crew ruling: mirrors `procurement.purchase_requests.view`).
SPARE_PART_VIEW = "procurement.spare_part_requests.view"
#: Either spare part grant opens the spare part reads; every one of them still narrows to the
#: caller's own, decidable or (admin) submitted requests, and stock to quantities only.
SPARE_PART_READ = (SPARE_PART_CREATE, SPARE_PART_VIEW)



def reads_documents(db: Any, current_user: Mapping[str, Any], slugs: Iterable[str]) -> bool:
    """Whether the caller holds one of the document-opening `slugs`, read the SAME way the route
    gate read them (`require_any_permission_with_api_key`: admin role, else the user's permission
    slugs; on an identity read every gate user). Fails closed: a lookup that raises means
    quantities only, never an error and never the documents."""
    from app.services.user_service import UserPermissionService, gate_user_ids

    wanted = set(slugs)
    try:
        service = UserPermissionService(db)
        for uid in gate_user_ids(current_user):
            if service.get_user_role_slugs(uid) & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"}:
                continue
            if not (wanted & set(service.get_user_permission_slugs(uid))):
                return False
        return True
    except Exception:  # noqa: BLE001 - fail closed, as the clearance check does
        return False

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
