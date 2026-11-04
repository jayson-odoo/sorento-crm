"""PO-LINK-HISTORY: one "first seen" audit event per PO line already linked to an S/O.

Data only, no DDL. From this release the AutoCount PO ingest writes a
``scm.po_line.book_so_change`` audit event every time it moves a line's S/O link
(``app/services/scm/po_link_history.py``). Lines linked before that have no history, so
this seeds ONE ``scm.po_line.book_so_seen`` event for every PO line that carries a
``from_so_line_ref`` and has no S/O link event yet:

    changed_at := the line's earliest AutoCount ``order_link_claim.claimed_at``
                  (Malaysian wall time, converted to UTC), else the line's own
                  ``created_at`` (already UTC)

That time is an UPPER bound ("linked on or before"), never the moment, and the screen says
so. Idempotent: a line with any S/O link event is skipped, so a rerun inserts nothing.

Cheap on production: it only READS ``purchase_order_lines`` (no lock beyond ACCESS SHARE,
nothing on that table is written) and appends to ``audit_logs`` in keyset batches of
``_BATCH`` lines. Expected size: one row per linked line (33,225 linked lines on the
7 Sep book copy, see ``order_link_service.book_so_numbers_by_ref``).

Written with Core `Table` constructs rather than raw SQL so a test's scratch schema
(``schema_translate_map``) is honoured; on production they name the real tables.

Revision ID: polh_0001_seen_backfill
Revises: oiod_0001_backfill
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "polh_0001_seen_backfill"
down_revision = "oiod_0001_backfill"
branch_labels = None
depends_on = None

EVENT_CHANGE = "scm.po_line.book_so_change"
EVENT_SEEN = "scm.po_line.book_so_seen"
_BATCH = 5000
# Real `Table`s on a private MetaData: a test's `schema_translate_map` rewrites a `Table`'s
# schema but not a lightweight `sa.table()` clause's.
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
    "products",
    _md, sa.Column("id", UUID(as_uuid=False)), sa.Column("product_code", sa.String)
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


def _batch_select(after):
    """The next `_BATCH` linked lines (by id) with no S/O link event, as audit rows."""
    # `claimed_at` is Malaysian wall time (`order_link_service._now()`, every claim writer
    # stamps it) while `audit_logs.changed_at` is UTC, like `created_at`: read it as
    # Asia/Kuala_Lumpur and store it as UTC, or the screen shows it 8 hours late.
    claim_utc = sa.func.timezone(
        "UTC", sa.func.timezone("Asia/Kuala_Lumpur", _claims.c.claimed_at)
    )
    first_claim = (
        sa.select(sa.func.min(claim_utc))
        .where(_claims.c.po_line_id == _lines.c.id, _claims.c.source == "autocount")
        .scalar_subquery()
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
        _audit.c.entity_type == "purchase_order_lines",
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
            sa.literal("purchase_order_lines"),
            sa.cast(_lines.c.id, sa.String),
            sa.literal("EVENT"),
            sa.literal(EVENT_SEEN),
            sa.literal("system"),
            sa.func.coalesce(first_claim, _lines.c.created_at),
            sa.func.jsonb_build_object("from_so_line_ref", _lines.c.from_so_line_ref),
            sa.func.concat(code, ": S/O ", label, " first seen (linked on or before this date)"),
            _lines.c.company_id,
            sa.literal("purchase_orders"),
            sa.cast(_lines.c.purchase_order_id, sa.String),
        )
        .select_from(_lines.outerjoin(_products, _products.c.id == _lines.c.product_id))
        .where(*where)
        .order_by(_lines.c.id)
        .limit(_BATCH)
    )


def upgrade() -> None:
    bind = op.get_bind()
    after = None
    while True:
        # One statement per batch; RETURNING hands back the line ids it seeded, and the
        # largest is the next batch's keyset cursor (UUID text sorts as Postgres sorts uuid).
        seeded = [
            row[0]
            for row in bind.execute(
                _audit.insert()
                .from_select(
                    [
                        "id", "entity_type", "entity_id", "action", "event", "actor_type",
                        "changed_at", "new_values", "description", "company_id",
                        "root_entity_type", "root_entity_id",
                    ],
                    _batch_select(after),
                )
                .returning(_audit.c.entity_id)
            )
        ]
        if len(seeded) < _BATCH:
            break
        after = max(seeded)


def downgrade() -> None:
    # audit_logs is append-only (#1281 S0): the seeded rows stay, as history does.
    pass
