"""Cross-Entity Activity Timeline service.

A human-readable view layered over the raw ``audit_logs`` table. Where the Audit
Logs page lists rows verbatim, this feed:

  1. Resolves ``entity_id`` -> a human ``entity_label`` + detail-page ``entity_href``
     per entity type (the FE must never render a UUID). Lookups are batched one
     query per entity type per page (no N+1). Hard-deleted rows fall back to the
     label snapshot in ``old_values`` (``"Order SO-5560 (deleted)"``) or a stable
     ``"{Prefix} {short-id} (deleted)"`` when even that is gone.
  2. Diffs ``old_values`` / ``new_values`` into ``changes[]`` with human field
     labels, skipping unchanged + noise columns.
  3. Returns the distinct ``actors`` in the current window so the FE user filter
     populates without a second round-trip.

The response shape matches exactly what the Activity Timeline UI consumes
(``ActivityItem`` with ``entity_type``, ``entity_label``, ``entity_href``,
``action``, ``actor_name``, ``summary``, ``changes[{field, from, to}]``,
``trace_id``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User
from app.models.complaints import Complaint
from app.models.order import Order
from app.models.procurement import Supplier, StockInquiry, PurchaseRequestHeader
from app.models.marketing import Promotion
from app.models.forms import Form
from app.models.tickets import Ticket
from app.models.product import Product


# --------------------------------------------------------------------------- #
# Entity registry                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _EntityCfg:
    """How to resolve one FE entity type from its audit rows."""

    fe_type: str
    # Values that may appear in ``audit_logs.entity_type`` for this family. The
    # audit listener defaults to ``__tablename__`` (plural) when a model does not
    # set ``__audit_entity_type__``, so we accept both singular + plural forms.
    stored_types: tuple[str, ...]
    model: Optional[type]
    # Ordered candidate columns for the display label (first non-empty wins).
    label_cols: tuple[str, ...]
    prefix: str
    # Detail-page href template; ``None`` when the FE has no detail route.
    href_template: Optional[str]


_REGISTRY: tuple[_EntityCfg, ...] = (
    _EntityCfg("complaint", ("complaint", "complaints"), Complaint,
               ("complaint_number",), "Complaint",
               "/complaint-management/complaints/{id}"),
    _EntityCfg("order", ("order", "orders"), Order,
               ("order_number",), "Order",
               "/order-management/orders/{id}"),
    _EntityCfg("user", ("user", "users"), User,
               ("name", "email"), "User",
               "/user-management/users/{id}"),
    _EntityCfg("supplier", ("supplier", "suppliers"), Supplier,
               ("supplier_name", "supplier_code"), "Supplier",
               "/procurement-management/suppliers/{id}"),
    _EntityCfg("promotion", ("promotion", "promotions"), Promotion,
               ("description",), "Promotion",
               "/marketing-management/promotions/{id}"),
    _EntityCfg("form", ("form", "forms"), Form,
               ("name", "code"), "Form", None),
    _EntityCfg("ticket", ("ticket", "tickets"), Ticket,
               ("ticket_number", "title"), "Ticket", None),
    _EntityCfg("stock_inquiry", ("stock_inquiry",), StockInquiry,
               ("inquiry_number",), "Stock Inquiry",
               "/procurement-management/stock-inquiries/{id}"),
    _EntityCfg("purchase_request", ("purchase_request",), PurchaseRequestHeader,
               ("request_number",), "Purchase Request",
               "/procurement-management/purchase-requests/{id}"),
    _EntityCfg("product", ("product", "products"), Product,
               ("product_code", "product_name"), "Product SKU", None),
)

# stored audit entity_type -> config, and fe_type -> config
_BY_STORED: dict[str, _EntityCfg] = {
    s: cfg for cfg in _REGISTRY for s in cfg.stored_types
}
_BY_FE: dict[str, _EntityCfg] = {cfg.fe_type: cfg for cfg in _REGISTRY}


# --------------------------------------------------------------------------- #
# Action mapping (stored <-> FE verb)                                         #
# --------------------------------------------------------------------------- #
# The audit listener writes "CREATE"; older/manual calls may write "INSERT".
_STORED_ACTIONS_FOR_FE = {
    "created": ("INSERT", "CREATE"),
    "updated": ("UPDATE",),
    "deleted": ("DELETE",),
    "imported": ("IMPORT",),
}


def _fe_action(stored: Optional[str]) -> str:
    s = (stored or "").upper()
    if s in ("INSERT", "CREATE"):
        return "created"
    if s == "DELETE":
        return "deleted"
    if s == "IMPORT":
        return "imported"
    return "updated"


# --------------------------------------------------------------------------- #
# Field diffing                                                               #
# --------------------------------------------------------------------------- #
# Auto-maintained / low-signal columns never worth showing as a change.
_NOISE_FIELDS = frozenset({
    "updated_at", "created_at", "last_synced_to_excel", "synced_to_excel",
    "portal_draft_at", "last_responded_at", "updated_time",
})

# Human labels for columns whose Title-Case would read oddly.
_FIELD_LABEL_ALIASES = {
    "approval_status": "Approval status",
    "is_active": "Active",
    "sla_response_due_at": "Response due",
    "sla_resolution_due_at": "Resolution due",
    "unit_price": "Unit price",
    "list_price": "List price",
    "cost_price": "Cost price",
    "end_date": "End date",
    "start_date": "Start date",
    "assigned_to": "Assignee",
    "delivery_order_number": "Delivery order",
    "product_code": "Product code",
}


def _field_label(col: str) -> str:
    if col in _FIELD_LABEL_ALIASES:
        return _FIELD_LABEL_ALIASES[col]
    words = col.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else col


def _fmt_value(v: Any) -> Optional[str]:
    """Stringify a value for display. ``None`` stays ``None`` (FE renders '—')."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    s = str(v)
    return s if len(s) <= 200 else s[:197] + "…"


def _build_changes(
    action: str, old_values: Optional[dict], new_values: Optional[dict]
) -> list[dict[str, Any]]:
    """Diff old/new into ``[{field, from, to}]``. Empty for INSERT/DELETE."""
    if _fe_action(action) != "updated":
        return []
    old = old_values or {}
    new = new_values or {}
    changes: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        if key in _NOISE_FIELDS:
            continue
        ov, nv = old.get(key), new.get(key)
        if ov == nv:
            continue
        changes.append(
            {"field": _field_label(key), "from": _fmt_value(ov), "to": _fmt_value(nv)}
        )
    return changes


def _summary(action: str, description: Optional[str], changes: list[dict]) -> Optional[str]:
    if description:
        return description
    if changes:
        c = changes[0]
        extra = f" (+{len(changes) - 1} more)" if len(changes) > 1 else ""
        return f"{c['field']}: {c['from'] or '—'} → {c['to'] or '—'}{extra}"
    return None


# --------------------------------------------------------------------------- #
# Label resolution                                                            #
# --------------------------------------------------------------------------- #
def _label_from_snapshot(cfg: _EntityCfg, row: AuditLog) -> Optional[str]:
    """Best-effort label from the audit row's own value snapshot (for deleted rows)."""
    for src in (row.new_values, row.old_values):
        if not src:
            continue
        for col in cfg.label_cols:
            val = src.get(col)
            if val:
                return f"{cfg.prefix} {val}"
    return None


def _short_id(entity_id: Any) -> str:
    s = str(entity_id) if entity_id else ""
    return s[:8] if s else "unknown"


def _resolve_labels(
    db: Session, rows: list[AuditLog]
) -> dict[tuple[str, str], tuple[str, Optional[str]]]:
    """Batch-resolve (entity_type, entity_id) -> (label, href).

    One query per entity type present in the page — never per row.
    """
    # Group entity ids by config. entity_id is coerced to str — some legacy rows
    # store it as a UUID object, and live-row label maps are keyed by str(id).
    ids_by_cfg: dict[str, set[str]] = {}
    for r in rows:
        cfg = _BY_STORED.get(r.entity_type)
        if cfg is None or cfg.model is None:
            continue
        ids_by_cfg.setdefault(cfg.fe_type, set()).add(str(r.entity_id))

    # Live-row label maps: fe_type -> {id: label}
    live: dict[str, dict[str, str]] = {}
    for fe_type, ids in ids_by_cfg.items():
        cfg = _BY_FE[fe_type]
        if not ids:
            continue
        try:
            records = (
                db.query(cfg.model)
                .filter(cfg.model.id.in_(list(ids)))
                .all()
            )
        except Exception:
            records = []
        m: dict[str, str] = {}
        for rec in records:
            label_val = None
            for col in cfg.label_cols:
                v = getattr(rec, col, None)
                if v:
                    label_val = str(v).strip()
                    break
            rec_id = str(getattr(rec, "id"))
            m[rec_id] = f"{cfg.prefix} {label_val}" if label_val else f"{cfg.prefix} {_short_id(rec_id)}"
        live[fe_type] = m

    resolved: dict[tuple[str, str], tuple[str, Optional[str]]] = {}
    for r in rows:
        eid = str(r.entity_id)
        cfg = _BY_STORED.get(r.entity_type)
        if cfg is None:
            # Unknown entity type — readable fallback, no href.
            pretty = str(r.entity_type).replace("_", " ").title()
            resolved[(r.entity_type, eid)] = (
                f"{pretty} {_short_id(eid)}", None
            )
            continue
        key = (r.entity_type, eid)
        label_map = live.get(cfg.fe_type, {})
        if eid in label_map:
            href = (
                cfg.href_template.format(id=eid)
                if cfg.href_template else None
            )
            resolved[key] = (label_map[eid], href)
        else:
            # Hard-deleted (or unresolvable) row: no live record.
            snap = _label_from_snapshot(cfg, r)
            base = snap or f"{cfg.prefix} {_short_id(eid)}"
            resolved[key] = (f"{base} (deleted)", None)
    return resolved


# --------------------------------------------------------------------------- #
# Query helpers                                                               #
# --------------------------------------------------------------------------- #
def _parse_day(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _stored_types_for(entity_types: Optional[list[str]]) -> Optional[list[str]]:
    """Map FE entity types -> stored audit entity_type values for filtering."""
    if not entity_types:
        return None
    stored: list[str] = []
    for et in entity_types:
        cfg = _BY_FE.get(et)
        if cfg is not None:
            stored.extend(cfg.stored_types)
        else:
            stored.append(et)  # pass through unknowns so filter still narrows
    return stored or None


def _apply_filters(
    query,
    *,
    stored_types: Optional[list[str]],
    action: Optional[str],
    user_id: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
    q: Optional[str],
    trace_id: Optional[str],
    include_user: bool = True,
):
    if stored_types:
        query = query.filter(AuditLog.entity_type.in_(stored_types))
    if action:
        stored_actions = _STORED_ACTIONS_FOR_FE.get(action.lower())
        if stored_actions:
            query = query.filter(AuditLog.action.in_(stored_actions))
    if include_user and user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.changed_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(
            AuditLog.changed_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(AuditLog.entity_id.ilike(like), AuditLog.description.ilike(like))
        )
    if trace_id:
        query = query.filter(AuditLog.trace_id == trace_id)
    return query


def _user_display_names(db: Session, user_ids: list[str]) -> dict[str, str]:
    """Map user_id -> name (email fallback). Mirrors audit_logs helper."""
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return {}
    users = db.query(User.id, User.name, User.email).filter(User.id.in_(ids)).all()
    return {
        str(u.id): (u.name.strip() if u.name and u.name.strip() else (u.email or str(u.id)))
        for u in users
    }


# --------------------------------------------------------------------------- #
# Public entrypoint                                                           #
# --------------------------------------------------------------------------- #
def get_activity_feed(
    db: Session,
    *,
    entity_types: Optional[list[str]] = None,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    trace_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Return ``{items, actors, pagination}`` for the activity timeline."""
    stored_types = _stored_types_for(entity_types)
    df = _parse_day(date_from)
    dt = _parse_day(date_to)

    base = db.query(AuditLog)
    filtered = _apply_filters(
        base,
        stored_types=stored_types,
        action=action,
        user_id=user_id,
        date_from=df,
        date_to=dt,
        q=q,
        trace_id=trace_id,
    )
    total = filtered.count()
    offset = (page - 1) * limit
    rows = (
        filtered.order_by(AuditLog.changed_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    labels = _resolve_labels(db, rows)
    actor_ids = list({str(r.user_id) for r in rows if r.user_id})
    actor_names = _user_display_names(db, actor_ids)

    items: list[dict[str, Any]] = []
    for r in rows:
        eid = str(r.entity_id)
        changes = _build_changes(r.action, r.old_values, r.new_values)
        cfg = _BY_STORED.get(r.entity_type)
        if r.action == "IMPORT":
            # Coarse import rows are job-keyed (entity_id = import job id, not a
            # live entity) — resolving it would render a bogus "(deleted)" label.
            # Use the human description ("Order tracking import X, N rows") instead.
            pretty = str(r.entity_type).replace("_", " ").title()
            label = r.description or f"{pretty} import"
            href = None
        else:
            label, href = labels.get((r.entity_type, eid), (eid, None))
        items.append({
            "id": str(r.id),
            "entity_type": cfg.fe_type if cfg else r.entity_type,
            "entity_id": eid,
            "entity_label": label,
            "entity_href": href,
            "action": _fe_action(r.action),
            "actor_id": str(r.user_id) if r.user_id else None,
            "actor_name": actor_names.get(str(r.user_id)) if r.user_id else "System",
            "actor_avatar_url": None,
            # changed_at is stored naive UTC — emit with a 'Z' so the browser
            # parses it as UTC (else it's read as local time and shows ~8h off in
            # MYT). The FE date helpers render it in Asia/Kuala_Lumpur.
            "changed_at": (
                (r.changed_at.isoformat() + "Z")
                if r.changed_at and r.changed_at.tzinfo is None
                else (r.changed_at.isoformat() if r.changed_at else None)
            ),
            "description": r.description,
            "summary": _summary(r.action, r.description, changes),
            "changes": changes,
            "trace_id": r.trace_id,
        })

    # Actors for the filter dropdown: distinct real users in the window,
    # ignoring the current user_id filter so switching users stays possible.
    actor_scope = _apply_filters(
        db.query(AuditLog.user_id).filter(AuditLog.user_id.isnot(None)),
        stored_types=stored_types,
        action=action,
        user_id=None,
        date_from=df,
        date_to=dt,
        q=q,
        trace_id=trace_id,
        include_user=False,
    ).distinct()
    scope_ids = [str(row[0]) for row in actor_scope.all() if row[0]]
    scope_names = _user_display_names(db, scope_ids)
    actors = sorted(
        ({"id": i, "name": scope_names.get(i, i)} for i in scope_ids),
        key=lambda a: a["name"].lower(),
    )

    return {
        "items": items,
        "actors": actors,
        "pagination": {"page": page, "limit": limit, "total": total},
    }
