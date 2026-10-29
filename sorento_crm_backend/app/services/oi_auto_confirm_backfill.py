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
from typing import Any, Dict, Mapping

import sqlalchemy as sa

from app.models.procurement import PurchaseOrderLine, SPOAllocation
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
)

_ZERO = Decimal("0")
BUY_VERBS = (IV_ORDER, IV_RESERVE_AND_ORDER, IV_ORDER_BACK)
_ROW_COLUMNS = (
    "id", "state", "verb", "qty", "redirected_to_pool", "ack_state",
    "bundled_qty", "bundled_with_row_id",
)


def _dec(value: Any) -> Decimal:
    return _ZERO if value is None else Decimal(str(value))


def live_link_filters(links, po_lines, spo_allocations):
    """A link is LIVE when its PO line is not cancelled and its SPO allocation is not
    retired (a reserve link names neither, so it always counts)."""
    return (
        sa.or_(
            links.c.po_line_id.is_(None),
            sa.func.coalesce(po_lines.c.line_status, "") != "cancelled",
        ),
        sa.or_(
            links.c.spo_allocation_id.is_(None),
            spo_allocations.c.retired_at.is_(None),
        ),
    )


def compute_done(rows: Mapping[str, Any], linked: Mapping[str, Decimal]) -> Dict[str, bool]:
    """`row id -> done` for every row in `rows` (objects exposing `id`, `state`, `verb`, `qty`,
    `redirected_to_pool`, `ack_state`, `bundled_qty`, `bundled_with_row_id`). `linked` is each
    row's LIVE linked qty. A rejected row reads done for what is bundled to it."""

    def own_done(row: Any) -> bool:
        return (
            row.state == INQUIRY_ACTIONED
            or row.verb not in BUY_VERBS
            or bool(row.redirected_to_pool)
            or linked.get(row.id, _ZERO) >= _dec(row.qty)
        )

    done: Dict[str, bool] = {}
    for row in rows.values():
        if row.ack_state == ACK_REJECTED:
            done[row.id] = True
        elif not row.bundled_with_row_id or _dec(row.bundled_qty) <= _ZERO:
            done[row.id] = own_done(row)
    for row in rows.values():
        if row.id in done:
            continue
        host_done = done.get(row.bundled_with_row_id)
        if host_done is None:
            host = rows.get(row.bundled_with_row_id)
            host_done = host is not None and own_done(host)
        done[row.id] = own_done(row) or (
            host_done and linked.get(row.id, _ZERO) + _dec(row.bundled_qty) >= _dec(row.qty)
        )
    return done


class _Facts:
    __slots__ = _ROW_COLUMNS

    def __init__(self, mapping):
        for name in _ROW_COLUMNS:
            setattr(self, name, mapping[name])
        self.id = str(self.id)
        if self.bundled_with_row_id:
            self.bundled_with_row_id = str(self.bundled_with_row_id)


def backfill_auto_confirm(connection) -> int:
    """Set every live, not-rejected row to the state the rule gives it: done -> `acknowledged`
    (by NULL, at now) when not already; not done and `acknowledged` -> `awaiting`, stamps
    cleared; `awaiting` / `changed` not done stay. `ack_override` is never written (a press
    before this shipped is not a manual decision). Idempotent. Returns rows changed."""
    rows_t = OrderInquiryRow.__table__
    links = OrderInquiryLink.__table__
    po_lines = PurchaseOrderLine.__table__
    spo_allocations = SPOAllocation.__table__

    rows: Dict[str, _Facts] = {}
    for mapping in connection.execute(
        sa.select(*[rows_t.c[name] for name in _ROW_COLUMNS])
    ).mappings():
        facts = _Facts(mapping)
        rows[facts.id] = facts
    if not rows:
        return 0
    live = connection.execute(
        sa.select(links.c.row_id, sa.func.sum(links.c.qty))
        .select_from(
            links.outerjoin(po_lines, po_lines.c.id == links.c.po_line_id).outerjoin(
                spo_allocations, spo_allocations.c.id == links.c.spo_allocation_id
            )
        )
        .where(*live_link_filters(links, po_lines, spo_allocations))
        .group_by(links.c.row_id)
    ).all()
    linked = {str(row_id): _dec(qty) for row_id, qty in live}
    done = compute_done(rows, linked)

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
