"""OI-AUTO-CONFIRM: the done rule, and the one-time pass that applies it to every row.

`compute_done` is the ONE predicate: `ProjectOrderInquiryService.auto_confirm` (live writes)
and `backfill_auto_confirm` (migration `oiac_0001_ack_override`) both call it, so the two
cannot come to disagree. A row is DONE when purchasing has nothing left to do on it: its
LIVE links cover its qty, or it is `actioned`, or its verb is not a buy verb, or it was
redirected to the pool, or it is a companion whose own links plus bundled qty cover it AND
whose host is done.

The backfill reads EXPLICIT columns of the mapped tables (never a whole mapped row, which
would select columns later migrations add) through Core, so it runs on a connection with a
`schema_translate_map` and on a fresh CI migrate alike.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import AbstractSet, Any, Dict, Mapping

import sqlalchemy as sa

from app.models.order import SalesOrderLine
from app.models.procurement import PurchaseOrderLine, SPOAllocation
from app.models.product import Product
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_REJECTED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    IV_ORDER,
    IV_ORDER_BACK,
    IV_RESERVE_AND_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrderLine,
)

_ZERO = Decimal("0")
BUY_VERBS = (IV_ORDER, IV_RESERVE_AND_ORDER, IV_ORDER_BACK)
_ROW_COLUMNS = (
    "id", "state", "verb", "qty", "redirected_to_pool", "ack_state",
    "bundled_qty", "bundled_with_row_id",
)


def _dec(value: Any) -> Decimal:
    return _ZERO if value is None else Decimal(str(value))


def live_cover_stmt(row_ids=None):
    """Per row: `(row_id, covered qty, newest link time, link count)` over the row's LIVE links.

    LIVE = the PO line is not cancelled, the SPO allocation is not retired, and (for a PO /
    SPO link) the document's product is the row's CURRENT item - an item swap leaves the old
    link in place but it no longer covers the new product. A reserve link names neither
    document, so it always counts. An item code no product carries skips the product check.
    """
    rows_t = OrderInquiryRow.__table__
    links = OrderInquiryLink.__table__
    po_lines = PurchaseOrderLine.__table__
    spo_allocations = SPOAllocation.__table__
    products = Product.__table__
    mirrors = ProjectSalesOrderLine.__table__
    code_product = (
        sa.select(products.c.id)
        .where(
            products.c.product_code == rows_t.c.item_code,
            products.c.company_id == rows_t.c.company_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    # The SAME reading `_resolve_product_id` gives the link writers: the reconciled line's
    # product first, the item code only as the fallback.
    row_product = sa.func.coalesce(
        sa.select(mirrors.c.product_id)
        .where(mirrors.c.id == rows_t.c.so_line_id)
        .scalar_subquery(),
        code_product,
    )
    stmt = (
        sa.select(
            links.c.row_id,
            sa.func.sum(links.c.qty),
            sa.func.max(links.c.linked_at),
            sa.func.count(links.c.id),
        )
        .select_from(
            links.join(rows_t, rows_t.c.id == links.c.row_id)
            .outerjoin(po_lines, po_lines.c.id == links.c.po_line_id)
            .outerjoin(spo_allocations, spo_allocations.c.id == links.c.spo_allocation_id)
        )
        .where(
            sa.or_(
                links.c.po_line_id.is_(None),
                sa.and_(
                    sa.func.coalesce(po_lines.c.line_status, "") != "cancelled",
                    sa.or_(row_product.is_(None), po_lines.c.product_id == row_product),
                ),
            ),
            sa.or_(
                links.c.spo_allocation_id.is_(None),
                sa.and_(
                    spo_allocations.c.retired_at.is_(None),
                    sa.or_(row_product.is_(None), spo_allocations.c.product_id == row_product),
                ),
            ),
        )
        .group_by(links.c.row_id)
    )
    if row_ids is not None:
        stmt = stmt.where(links.c.row_id.in_(list(row_ids)))
    return stmt


def cancelled_line_stmt(row_ids=None):
    """Ids of the rows whose core sales order line is cancelled."""
    rows_t = OrderInquiryRow.__table__
    mirrors = ProjectSalesOrderLine.__table__
    core_lines = SalesOrderLine.__table__
    stmt = (
        sa.select(rows_t.c.id)
        .select_from(
            rows_t.join(mirrors, mirrors.c.id == rows_t.c.so_line_id).join(
                core_lines, core_lines.c.id == mirrors.c.core_sales_order_line_id
            )
        )
        .where(core_lines.c.line_status == "cancelled")
    )
    if row_ids is not None:
        stmt = stmt.where(rows_t.c.id.in_(list(row_ids)))
    return stmt


def compute_done(
    rows: Mapping[str, Any],
    linked: Mapping[str, Decimal],
    live_links: Mapping[str, int] | None = None,
    cancelled_line: AbstractSet[str] = frozenset(),
) -> Dict[str, bool]:
    """`row id -> done` for every row in `rows` (objects exposing `id`, `state`, `verb`, `qty`,
    `redirected_to_pool`, `ack_state`, `ack_override`, `bundled_qty`, `bundled_with_row_id`).
    `linked` is each row's LIVE linked qty (`live_cover_stmt`), `live_links` its live link
    count, `cancelled_line` the rows on a cancelled sales order line. A manual Confirm is done,
    a manual Unconfirm is not. A rejected row reads done for itself but is no host."""
    live_links = live_links or {}

    def own_done(row: Any) -> bool:
        if row.ack_override == "confirmed":
            return True
        if row.ack_override == "unconfirmed":
            return False
        if row.id in cancelled_line:
            # AC-AC-10e (owner 30 Oct): nothing to buy on a cancelled SO line, whatever its
            # links or verb; purchasing never acts on it.
            return True
        if row.state == INQUIRY_ACTIONED or row.verb not in BUY_VERBS or row.redirected_to_pool:
            return True
        return linked.get(row.id, _ZERO) >= _dec(row.qty)

    done: Dict[str, bool] = {}
    for row in rows.values():
        if row.ack_state == ACK_REJECTED:
            done[row.id] = True
        elif not row.bundled_with_row_id or _dec(row.bundled_qty) <= _ZERO:
            done[row.id] = own_done(row)
    for row in rows.values():
        if row.id in done:
            continue
        host = rows.get(row.bundled_with_row_id)
        host_done = (
            host is not None
            and host.ack_state != ACK_REJECTED
            and done.get(host.id, own_done(host))
        )
        done[row.id] = own_done(row) or (
            host_done and linked.get(row.id, _ZERO) + _dec(row.bundled_qty) >= _dec(row.qty)
        )
    return done


class _Facts:
    __slots__ = _ROW_COLUMNS + ("ack_override",)

    def __init__(self, mapping):
        for name in _ROW_COLUMNS:
            setattr(self, name, mapping[name])
        self.ack_override = None  # the backfill runs before any press exists
        self.id = str(self.id)
        if self.bundled_with_row_id:
            self.bundled_with_row_id = str(self.bundled_with_row_id)


def backfill_auto_confirm(connection) -> int:
    """Set every live, not-rejected row to the state the rule gives it: done -> `acknowledged`
    (by NULL, at now) when not already; not done and `acknowledged` -> `awaiting`, stamps
    cleared; `awaiting` / `changed` not done stay. `ack_override` is never written (a press
    before this shipped is not a manual decision). Idempotent. Returns rows changed."""
    rows_t = OrderInquiryRow.__table__

    rows: Dict[str, _Facts] = {}
    for mapping in connection.execute(
        sa.select(*[rows_t.c[name] for name in _ROW_COLUMNS])
    ).mappings():
        facts = _Facts(mapping)
        rows[facts.id] = facts
    if not rows:
        return 0
    live = connection.execute(live_cover_stmt()).all()
    linked = {str(row_id): _dec(qty) for row_id, qty, _newest, _count in live}
    counts = {str(row_id): int(count) for row_id, _qty, _newest, count in live}
    cancelled = {str(row_id) for (row_id,) in connection.execute(cancelled_line_stmt())}
    done = compute_done(rows, linked, counts, cancelled)

    to_done = [
        {"b_id": r.id}
        for r in rows.values()
        if r.state != INQUIRY_CANCELLED
        and r.ack_state != ACK_REJECTED
        and done[r.id]
        and r.ack_state != ACK_ACKNOWLEDGED
    ]
    to_awaiting = [
        {"b_id": r.id}
        for r in rows.values()
        if r.state != INQUIRY_CANCELLED
        and r.ack_state == ACK_ACKNOWLEDGED
        and not done[r.id]
    ]
    now = datetime.utcnow()
    if to_done:
        connection.execute(
            sa.update(rows_t)
            .where(rows_t.c.id == sa.bindparam("b_id"))
            .values(ack_state=ACK_ACKNOWLEDGED, acknowledged_by=None, acknowledged_at=now),
            to_done,
        )
    if to_awaiting:
        connection.execute(
            sa.update(rows_t)
            .where(rows_t.c.id == sa.bindparam("b_id"))
            .values(ack_state=ACK_AWAITING, acknowledged_by=None, acknowledged_at=None),
            to_awaiting,
        )
    return len(to_done) + len(to_awaiting)
