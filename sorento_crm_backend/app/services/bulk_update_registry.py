"""Whitelisted bulk-update registry.

The whole point of this module is that there is **no** generic "write any column"
path. Each resource registers a small allow-list of editable fields (and, for
enum/bool fields, their allowed values) plus a per-row updater that goes through
that resource's **existing service update method** - so validation, business
rules, side effects and audit all run exactly as they do for a single-record
edit. Rows the normal path rejects come back in ``skipped`` with a human reason;
the rest commit. Partial success, never all-or-nothing.

Contract (see the FE service header for the mirrored FE contract):

    POST /api/v1/<resource>/bulk-update
    body: { ids: string[] (1..500, deduped), field: string, value: any }
    200:  { updated: int, skipped: [{ id, label, reason }] }
    400:  field not on the whitelist, or value not allowed for the field

A resource opts in by calling :func:`register_bulk_resource`. The endpoint layer
just calls :func:`run_bulk_update` - it never touches columns directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.services.error_handler import AppException, handle_validation_error

# Hard cap on selection size. Mirrors the email-outbox bulk cap; the endpoint's
# Pydantic model also enforces this so an over-cap request 422s before we get here.
MAX_BULK_IDS = 500


@dataclass
class BulkField:
    """One whitelisted editable field for a resource.

    ``coerce`` takes the raw JSON value and returns the value handed to
    ``update_one`` (already validated / normalized). It MUST raise ``ValueError``
    when the value isn't allowed for this field - a globally-invalid value is a
    request error (400), not a silent per-row skip.
    """

    key: str
    label: str
    coerce: Callable[[Any], Any]


@dataclass
class BulkUpdateResource:
    """Registration for a bulk-updatable resource."""

    resource: str
    # (db, id) -> row or None
    load_row: Callable[[Session, str], Any]
    # (row) -> human-readable label (NEVER a raw uuid surfaced to the UI)
    load_label: Callable[[Any], str]
    # (db, row, field, coerced_value, acting_user) -> None. MUST route through the
    # resource's existing service update method so side effects + audit fire.
    update_one: Callable[[Session, Any, str, Any, Optional[dict]], None]
    fields: dict[str, BulkField]


_REGISTRY: dict[str, BulkUpdateResource] = {}


def register_bulk_resource(res: BulkUpdateResource) -> None:
    """Register (or replace) a resource's bulk-update config."""
    _REGISTRY[res.resource] = res


def get_bulk_resource(resource: str) -> Optional[BulkUpdateResource]:
    return _REGISTRY.get(resource)


def _exc_message(exc: Exception) -> str:
    """Extract a human message from an AppException (detail dict) or any error."""
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return detail.get("message") or "Update failed."
    if detail:
        return str(detail)
    return str(exc) or "Update failed."


def run_bulk_update(
    db: Session,
    resource_key: str,
    ids: list[str],
    field: str,
    value: Any,
    user: Optional[dict] = None,
) -> dict[str, Any]:
    """Apply ``field = value`` to each of ``ids`` via the resource's normal update
    path, returning a partial-success summary.

    - Field not on the resource's whitelist -> 400 (no raw column write is ever
      reachable).
    - Value not allowed for the field -> 400 (validated once, globally).
    - Per row: not found, or rejected by the normal update path -> collected in
      ``skipped`` with a human ``label`` + ``reason``; the batch continues.
    """
    res = get_bulk_resource(resource_key)
    if res is None:
        # Programmer error - a route wired to an unregistered resource.
        raise handle_validation_error(f"Bulk update is not configured for '{resource_key}'.")

    spec = res.fields.get(field)
    if spec is None:
        allowed = ", ".join(sorted(res.fields)) or "(none)"
        raise handle_validation_error(
            f"Field '{field}' cannot be bulk-updated on {resource_key}. Allowed fields: {allowed}."
        )

    # Global allow-list / coercion. A value that isn't valid for the field at all
    # is a request error, not a per-row skip that would silently no-op the batch.
    try:
        coerced = spec.coerce(value)
    except (ValueError, TypeError) as exc:
        raise handle_validation_error(
            str(exc) or f"Value is not allowed for field '{field}'."
        )

    # Dedup ids, preserving order.
    seen: set[str] = set()
    unique_ids: list[str] = []
    for rid in ids:
        if rid not in seen:
            seen.add(rid)
            unique_ids.append(rid)

    updated = 0
    skipped: list[dict[str, str]] = []
    for rid in unique_ids:
        label = rid
        try:
            row = res.load_row(db, rid)
            if row is None:
                skipped.append({"id": rid, "label": rid, "reason": "Record not found."})
                continue
            label = res.load_label(row) or rid
            res.update_one(db, row, field, coerced, user)
            updated += 1
        except AppException as exc:
            # Normal update path rejected this row (validation / business rule).
            db.rollback()
            skipped.append({"id": rid, "label": label, "reason": _exc_message(exc)})
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort the batch
            db.rollback()
            skipped.append({"id": rid, "label": label, "reason": _exc_message(exc)})

    return {"updated": updated, "skipped": skipped}


# ---------------------------------------------------------------------------
# Resource registrations
# ---------------------------------------------------------------------------
# Registered at import time. `app.main` imports this module (via the router) so
# the registry is populated before any request is served.


def _coerce_bool(value: Any) -> bool:
    """Coerce a whitelisted active/inactive value to a bool.

    The FE Select emits string values ("true"/"false"); n8n / API callers may send
    a real bool. Anything else is rejected so a typo can't flip a flag silently.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "active", "yes"):
            return True
        if low in ("false", "0", "inactive", "no"):
            return False
    raise ValueError("Status must be Active or Inactive.")


def _supplier_load_row(db: Session, rid: str):
    from app.models.procurement import Supplier

    return db.query(Supplier).filter(Supplier.id == rid).first()


def _supplier_label(row) -> str:
    return getattr(row, "supplier_name", None) or getattr(row, "supplier_code", None) or str(row.id)


def _supplier_update_one(db: Session, row, field: str, value: Any, user: Optional[dict]) -> None:
    # Route through the EXISTING single-record update service so validation,
    # `updated_at`, and the `__audit_track__` audit-log listener all fire - no raw
    # setattr+commit here.
    from app.schemas.procurement import SupplierUpdate
    from app.services.procurement_service import SupplierService

    SupplierService(db).update_supplier(str(row.id), SupplierUpdate(**{field: value}))


register_bulk_resource(
    BulkUpdateResource(
        resource="suppliers",
        load_row=_supplier_load_row,
        load_label=_supplier_label,
        update_one=_supplier_update_one,
        fields={
            "is_active": BulkField(key="is_active", label="Status", coerce=_coerce_bool),
        },
    )
)
