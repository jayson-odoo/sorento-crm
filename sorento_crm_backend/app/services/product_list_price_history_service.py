"""A product's list-price history, for the products list's List Price lightbox
(LIST-PRICE-CHANGE-UI, plan documentation/plans/products/PLAN-list-price-change-ui-08nov.md).

Read from the audit trail, the only place a product's earlier prices live:

* every ``product`` UPDATE row whose ``new_values`` carries ``list_price`` (the flush listener
  writes only the changed keys, so the key's presence means the price was written), skipping
  a row that restates the same number;
* the product's CREATE row as one "Initial price" row (owner, 8 Nov, Q5), behind
  ``INCLUDE_INITIAL_PRICE`` so it can be switched off in one line.

Credited by the #2228 digest's rule (``_list_price_sources`` in
``product_watched_field_notify_service``): an integration is ``SYNC_SOURCE_LABEL``, a staff
user is their name (else email), any other actor is unnamed. The rule is restated in SQL here
because the owner's lightbox is a server-paged, server-sorted DataGrid (Q3), and "by" is one of
its sortable columns.

The caller gates visibility by loading the product through the company-scoped ORM first; this
module reads ``audit_logs`` by that one product id only (raw SQL: ``audit_logs`` is not
company-scoped, see ``AuditLog.company_id``).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.product_watched_field_notify_service import SYNC_SOURCE_LABEL

#: Owner Q5 ("include the price set at create time"): crew is confirming the reading; flip to
#: False to show changes only.
INCLUDE_INITIAL_PRICE = True

# A JSON price as numeric, or NULL when the stored text is not a plain decimal (never a cast
# error that would fail the whole read).
_NUM = (
    "CASE WHEN ({x}) ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN ({x})::numeric END"
)

#: Sort key -> SQL expression over the ``h`` rows below. Anything else sorts by date.
_SORTS = {
    "changed_at": "changed_at",
    "old_price": "old_price",
    "new_price": "new_price",
    "change_pct": "change_pct",
    "changed_by": "changed_by",
}


def list_price_history(
    db: Session,
    product_id: str,
    *,
    page: int = 1,
    limit: int = 10,
    sort: str = "changed_at",
    direction: str = "desc",
) -> dict:
    """``{"data": [...], "pagination": {"total", "page", "limit"}}``, the DataGrid shape.

    Each row: ``id`` (the audit row's), ``kind`` (``change`` | ``initial``), ``changed_at``
    (naive UTC ISO), ``old_price`` / ``new_price`` (floats, null when absent or unreadable),
    ``change_pct`` (one decimal, null from 0 and on the initial row), ``changed_by``.
    Nulls sort last in both directions; ties fall back to newest first.
    """
    sort_sql = _SORTS.get(sort, "changed_at")
    dir_sql = "ASC" if direction == "asc" else "DESC"
    actions = "('UPDATE', 'CREATE')" if INCLUDE_INITIAL_PRICE else "('UPDATE')"
    old_num = _NUM.format(x="a.old_values ->> 'list_price'")
    new_num = _NUM.format(x="a.new_values ->> 'list_price'")

    cte = f"""
        WITH raw AS (
            SELECT a.id, a.action, a.changed_at, a.actor_type, a.user_id,
                   CASE WHEN a.action = 'CREATE' THEN NULL ELSE {old_num} END AS old_price,
                   {new_num} AS new_price
            FROM audit_logs a
            WHERE a.entity_type = 'product' AND a.entity_id = :pid
              AND a.action IN {actions}
              AND a.new_values ? 'list_price'
        ), h AS (
            SELECT r.id, r.changed_at, r.old_price, r.new_price,
                   CASE WHEN r.action = 'CREATE' THEN 'initial' ELSE 'change' END AS kind,
                   CASE WHEN r.action = 'CREATE' THEN NULL
                        ELSE round((r.new_price - r.old_price) / NULLIF(r.old_price, 0) * 100, 1)
                   END AS change_pct,
                   CASE r.actor_type
                        WHEN 'integration' THEN :sync_label
                        WHEN 'user' THEN COALESCE(NULLIF(u.name, ''), u.email)
                   END AS changed_by
            FROM raw r
            LEFT JOIN users u ON r.actor_type = 'user' AND u.id::text = r.user_id::text
            WHERE r.action = 'CREATE' OR r.old_price IS DISTINCT FROM r.new_price
        )
    """
    params = {"pid": str(product_id), "sync_label": SYNC_SOURCE_LABEL}
    sql = cte + f"""
        SELECT h.*, count(*) OVER () AS total
        FROM h
        ORDER BY {sort_sql} {dir_sql} NULLS LAST, changed_at DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(sql), {**params, "limit": limit, "offset": (page - 1) * limit}).all()
    if rows:
        total = int(rows[0].total)
    else:
        # No history, or a page past the last one: no row carries the window count.
        total = int(db.execute(text(cte + " SELECT count(*) FROM h"), params).scalar() or 0)

    def _f(value):
        return float(value) if value is not None else None

    data = [
        {
            "id": str(r.id),
            "kind": r.kind,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            "old_price": _f(r.old_price),
            "new_price": _f(r.new_price),
            "change_pct": _f(r.change_pct),
            "changed_by": r.changed_by,
        }
        for r in rows
    ]
    return {"data": data, "pagination": {"total": total, "page": page, "limit": limit}}
