"""A product's list-price change history, for the products list's List Price lightbox
(LIST-PRICE-CHANGE-UI, plan documentation/plans/products/PLAN-list-price-change-ui-08nov.md).

Read from the audit trail, the only place a product's earlier prices live: every ``product``
UPDATE row whose ``new_values`` carries ``list_price`` (the flush listener writes only the
changed keys, so the key's presence means the price was written). A row that restates the
same price is skipped. A product's first price (its CREATE row) is not a change. Credited by
the #2228 digest's own rule, ``audit_source_labels``.

The caller gates visibility by loading the product through the company-scoped ORM first;
this module reads ``audit_logs`` by that product's id only.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.product_watched_field_notify_service import audit_source_labels

#: Rows returned; the rest are counted in ``total`` and flagged ``truncated``.
HISTORY_LIMIT = 50


def _price(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _pct(old: Optional[Decimal], new: Optional[Decimal]) -> Optional[float]:
    if old is None or new is None or old == 0:
        return None
    return float(round((new - old) / old * 100, 1))


def list_price_history(db: Session, product_id: str, limit: int = HISTORY_LIMIT) -> dict:
    """``{"data": [...newest first...], "total": n, "truncated": bool}``.

    Each row: ``changed_at`` (naive UTC), ``old_price``, ``new_price`` (floats, or null when
    the audit value is unreadable), ``change_pct`` (one decimal; null from 0), ``changed_by``.
    """
    # Raw SQL: audit_logs is not company-scoped (see AuditLog.company_id) and the filter
    # is the one product id the caller already proved visible. The no-op guard compares
    # the JSON text, so "10.00" vs "10.0" would still count; the Decimal check below
    # drops those too.
    where = (
        "entity_type = 'product' AND action = 'UPDATE' AND entity_id = :pid "
        "AND new_values ? 'list_price' "
        "AND (old_values ->> 'list_price') IS DISTINCT FROM (new_values ->> 'list_price')"
    )
    rows = db.execute(
        text(
            "SELECT id, changed_at, actor_type, user_id, "
            "old_values ->> 'list_price' AS old_price, new_values ->> 'list_price' AS new_price "
            f"FROM audit_logs WHERE {where} ORDER BY changed_at DESC, id DESC"
        ),
        {"pid": str(product_id)},
    ).all()

    changes = []
    for row in rows:
        old, new = _price(row.old_price), _price(row.new_price)
        if old is not None and new is not None and old == new:
            continue
        changes.append((row, old, new))

    total = len(changes)
    kept = changes[:limit]
    labels = audit_source_labels(db, {str(r.id): (r.actor_type, r.user_id) for r, _, _ in kept})
    data = [
        {
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            "old_price": float(old) if old is not None else None,
            "new_price": float(new) if new is not None else None,
            "change_pct": _pct(old, new),
            "changed_by": labels.get(str(r.id)),
        }
        for r, old, new in kept
    ]
    return {"data": data, "total": total, "truncated": total > limit}
