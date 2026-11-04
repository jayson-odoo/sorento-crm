"""PO-LINK-HISTORY: when and how a purchase-order line got its S/O link.

The S/O a PO line is raised for is `purchase_order_lines.from_so_line_ref`, written only by
the AutoCount PO ingest, and the line table is audit-skipped (`__audit_skip__`: the sync
writes thousands of line rows a day). So the ingest writes ONE explicit audit EVENT per link
change instead (`record_changes`), and nothing on a re-push that changes nothing. The PO
detail reads the latest one per line back (`latest_by_line`) for the S/O cell's popover,
and the PO History tab reads them through the audit trail (they roll up to the PO header).

AutoCount never says WHO moved a link, so the row carries the ingest's own actor (the
integration) and nothing more. Plan: documentation/plans/procurement/PLAN-po-link-history-04nov.md.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.product import Product
from app.services import audit_service
from app.services.scm import order_link_service

#: A link change the AutoCount PO sync wrote (old and new ref, either may be None).
EVENT_CHANGE = "scm.po_line.book_so_change"
#: The backfill's "first seen" row for a line linked before history began. Its time is an
#: upper bound (the line's earliest AutoCount claim, else its created_at), not the moment.
EVENT_SEEN = "scm.po_line.book_so_seen"

_ENTITY = "purchase_order_lines"
_ROOT = "purchase_orders"

log = logging.getLogger(__name__)


def _label(ref: Optional[str], number: Optional[str]) -> str:
    if not ref:
        return "none"
    # Never the ref itself: it is a machine key.
    return number or "an S/O not held here"


def record_changes(
    db: Session,
    changes: Sequence[tuple[Any, Optional[str], Optional[str]]],
    *,
    purchase_order_id: str,
) -> None:
    """One EVENT row per `(line, old_ref, new_ref)` whose two refs differ.

    Called by the ingest inside the record's savepoint, so a record that fails leaves no
    event behind. ONE sales-order lookup for the whole batch, never one per line.
    """
    moved = [(line, old, new) for line, old, new in changes if (old or None) != (new or None)]
    if not moved:
        return
    numbers = order_link_service.book_so_numbers_by_ref(
        db, [ref for _, old, new in moved for ref in (old, new) if ref]
    )
    # By id, not `line.product`: a line this sync just created has no product loaded.
    codes = dict(
        db.query(Product.id, Product.product_code)
        .filter(Product.id.in_({str(line.product_id) for line, _, _ in moved if line.product_id}))
        .all()
    )
    for line, old, new in moved:
        old_no = numbers.get(old) if old else None
        new_no = numbers.get(new) if new else None
        item = codes.get(str(line.product_id)) or "Line"
        audit_service.log_audit(
            db,
            _ENTITY,
            str(line.id),
            "EVENT",
            event=EVENT_CHANGE,
            old_values={"from_so_line_ref": old or None, "so_number": old_no},
            new_values={"from_so_line_ref": new or None, "so_number": new_no},
            description=f"{item}: S/O {_label(old, old_no)} → {_label(new, new_no)}",
            company_id=str(line.company_id) if line.company_id else None,
            root_entity_type=_ROOT,
            root_entity_id=str(purchase_order_id),
            skip_flush=True,
        )


def latest_by_line(db: Session, line_ids: Iterable[str]) -> dict[str, dict]:
    """Line id -> its latest S/O link event, as the PO detail serves it (`book_so_link`).

    Two reads for the whole order: the latest event per line, and one lookup resolving the
    previous refs to sales-order numbers NOW (an order pushed after the change still names).
    """
    ids = [str(i) for i in line_ids]
    if not ids:
        return {}
    rows = (
        db.query(AuditLog.entity_id, AuditLog.event, AuditLog.changed_at, AuditLog.old_values)
        .filter(
            AuditLog.entity_type == _ENTITY,
            AuditLog.entity_id.in_(ids),
            AuditLog.event.in_((EVENT_CHANGE, EVENT_SEEN)),
        )
        .distinct(AuditLog.entity_id)
        .order_by(AuditLog.entity_id, AuditLog.changed_at.desc(), AuditLog.id.desc())
        .all()
    )
    previous = {
        str(r.entity_id): (r.old_values or {}).get("from_so_line_ref")
        for r in rows
        if r.event == EVENT_CHANGE
    }
    numbers = order_link_service.book_so_numbers_by_ref(db, [p for p in previous.values() if p])
    out: dict[str, dict] = {}
    for r in rows:
        line_id = str(r.entity_id)
        if r.event == EVENT_SEEN:
            # Earlier history was never recorded: whether it had a previous S/O is unknown.
            out[line_id] = {
                "changed_at": r.changed_at.isoformat(),
                "estimated": True,
                "previous_linked": None,
                "previous_so_number": None,
            }
            continue
        prev = previous.get(line_id)
        out[line_id] = {
            "changed_at": r.changed_at.isoformat(),
            "estimated": False,
            "previous_linked": bool(prev),
            "previous_so_number": numbers.get(prev) if prev else None,
        }
    return out


# --------------------------------------------------------------------------- seen backfill
# POLH-BACKFILL-ASYNC: this ran inside the polh_0001 migration until the 5 Nov release, where it
# took ~19 s a batch on the prod clone (a Seq Scan of `scm.order_link_claim` per line: no index on
# `po_line_id`), blue never got healthy inside blue/green's 240 s and every pending revision
# rolled back. It now runs after the backend starts (`scripts/backfill_po_link_seen.py`).
#
# Private Core `Table`s, not the models: a test's `schema_translate_map` still applies, and the
# ORM company-scope filter (fail-closed with no scope set, as in a start-time script) never does.
BACKFILL_BATCH = 5000
_md = sa.MetaData()
_lines = sa.Table(
    "purchase_order_lines",
    _md,
    sa.Column("id", UUID(as_uuid=False)),
    sa.Column("purchase_order_id", UUID(as_uuid=False)),
    sa.Column("product_id", UUID(as_uuid=False)),
    sa.Column("company_id", UUID(as_uuid=False)),
    sa.Column("from_so_line_ref", sa.String),
    sa.Column("created_at", sa.DateTime),
)
_products = sa.Table(
    "products", _md, sa.Column("id", UUID(as_uuid=False)), sa.Column("product_code", sa.String)
)
_sales_orders = sa.Table(
    "sales_orders",
    _md,
    sa.Column("company_id", UUID(as_uuid=False)),
    sa.Column("so_number", sa.String),
    sa.Column("source_ref", sa.String),
)
_claims = sa.Table(
    "order_link_claim",
    _md,
    sa.Column("po_line_id", UUID(as_uuid=False)),
    sa.Column("source", sa.String),
    sa.Column("claimed_at", sa.DateTime),
    schema="scm",
)
_audit = sa.Table(
    "audit_logs",
    _md,
    sa.Column("id", UUID(as_uuid=False)),
    sa.Column("entity_type", sa.String),
    sa.Column("entity_id", sa.String),
    sa.Column("action", sa.String),
    sa.Column("event", sa.String),
    sa.Column("actor_type", sa.String),
    sa.Column("changed_at", sa.DateTime),
    sa.Column("new_values", JSONB),
    sa.Column("description", sa.Text),
    sa.Column("company_id", UUID(as_uuid=False)),
    sa.Column("root_entity_type", sa.String),
    sa.Column("root_entity_id", sa.String),
)
_SEEN_COLUMNS = [
    "id", "entity_type", "entity_id", "action", "event", "actor_type", "changed_at",
    "new_values", "description", "company_id", "root_entity_type", "root_entity_id",
]


def _seen_batch(after: Optional[str], batch: int):
    """The next `batch` linked lines (by id) with no S/O link event, as audit rows."""
    # `claimed_at` is Malaysian wall time (`order_link_service._now()`, every claim writer
    # stamps it) while `audit_logs.changed_at` is UTC, like `created_at`: read it as
    # Asia/Kuala_Lumpur and store it as UTC, or the screen shows it 8 hours late.
    # Aggregated ONCE per batch and merge-joined (101 ms a batch on the prod clone), never a
    # correlated min() per line (18.7 s).
    first_claim = (
        sa.select(
            _claims.c.po_line_id,
            sa.func.min(
                sa.func.timezone("UTC", sa.func.timezone("Asia/Kuala_Lumpur", _claims.c.claimed_at))
            ).label("at"),
        )
        .where(_claims.c.source == "autocount", _claims.c.po_line_id.isnot(None))
        .group_by(_claims.c.po_line_id)
        .subquery("first_claim")
    )
    doc_key = sa.func.concat(
        sa.func.split_part(_lines.c.from_so_line_ref, ":", 1),
        ":",
        sa.func.split_part(_lines.c.from_so_line_ref, ":", 2),
    )
    so_number = (
        sa.select(_sales_orders.c.so_number)
        .where(
            _sales_orders.c.source_ref == doc_key,
            _sales_orders.c.company_id == _lines.c.company_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    has_event = sa.exists().where(
        _audit.c.entity_type == _ENTITY,
        _audit.c.entity_id == sa.cast(_lines.c.id, sa.String),
        _audit.c.event.in_((EVENT_CHANGE, EVENT_SEEN)),
    )
    code = sa.func.coalesce(_products.c.product_code, "Line")
    label = sa.func.coalesce(so_number, "an S/O not held here")
    where = [
        _lines.c.from_so_line_ref.isnot(None),
        _lines.c.from_so_line_ref != "",
        ~has_event,
    ]
    if after is not None:
        where.append(_lines.c.id > after)
    return (
        sa.select(
            sa.func.gen_random_uuid(),
            sa.literal(_ENTITY),
            sa.cast(_lines.c.id, sa.String),
            sa.literal("EVENT"),
            sa.literal(EVENT_SEEN),
            sa.literal("system"),
            sa.func.coalesce(first_claim.c.at, _lines.c.created_at),
            sa.func.jsonb_build_object("from_so_line_ref", _lines.c.from_so_line_ref),
            sa.func.concat(code, ": S/O ", label, " first seen (linked on or before this date)"),
            _lines.c.company_id,
            sa.literal(_ROOT),
            sa.cast(_lines.c.purchase_order_id, sa.String),
        )
        .select_from(
            _lines.outerjoin(_products, _products.c.id == _lines.c.product_id).outerjoin(
                first_claim, first_claim.c.po_line_id == _lines.c.id
            )
        )
        .where(*where)
        .order_by(_lines.c.id)
        .limit(batch)
    )


def backfill_seen(db: Session, *, batch: int = BACKFILL_BATCH) -> int:
    """One `EVENT_SEEN` row per PO line carrying a `from_so_line_ref` and no S/O link event yet.

    ``changed_at`` is the line's earliest AutoCount claim (MYT read as UTC), else its
    ``created_at``: an upper bound ("linked on or before"), never the moment. One INSERT ...
    SELECT and one COMMIT per batch, so a run that dies keeps what it finished and the next run's
    NOT EXISTS skips it; a rerun over a seeded book inserts nothing. A line the ingest moves
    before this reaches it already has a change event, so it is skipped (its ref is no longer the
    pre-history one). Returns the rows inserted.
    """
    total = 0
    after: Optional[str] = None
    while True:
        # Connection.execute, not Session.execute: no ORM execute hooks on a Core insert.
        seeded = [
            row[0]
            for row in db.connection().execute(
                _audit.insert()
                .from_select(_SEEN_COLUMNS, _seen_batch(after, batch))
                .returning(_audit.c.entity_id)
            )
        ]
        db.commit()
        total += len(seeded)
        if seeded:
            log.info("po link seen backfill: %d rows (%d so far)", len(seeded), total)
        if len(seeded) < batch:
            return total
        # RETURNING hands back the line ids it seeded; the largest is the next keyset cursor
        # (UUID text sorts as Postgres sorts uuid).
        after = max(seeded)


__all__ = ["EVENT_CHANGE", "EVENT_SEEN", "backfill_seen", "latest_by_line", "record_changes"]
