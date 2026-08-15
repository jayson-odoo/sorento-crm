"""Remember what the GRN sheet said each line was received against.

`picking_lines` carried only `spo_allocation_id`, so a line whose SPO had no
allocation yet was written with NULL and nothing else: the sheet's claim was gone
the moment the import ended, and nothing could revisit the line when the
allocation arrived. `spo_number_raw` is that memory - the single SPO the import
resolved for the line (its own "Our PO No.", else the header's single-SPO
fallback), stored whether or not it matched.

Faithful to the sheet: no case folding, no separator rewriting. The tolerating is
`_spo_match_key`'s job at match time. A multi-SPO cell stores NULL, because a
joined value names no single allocation and would put a claim on screen that the
scalar matcher can never honour.

The index is the forward-matching query itself - the match key of UNLINKED lines.
`upper` and `regexp_replace` are IMMUTABLE, so the expression is indexable, and it
strips exactly what `procurement_service._spo_match_key` strips; a test asserts the
two agree, because a candidate found in SQL that the Python comparison then
rejects is the classic failure of a Python/SQL normalizer pair.

The backfill makes the EXISTING GRN corpus display honestly. It does not itself
run forward matching - operators who want historical links repaired keep using
`scripts/backfill_grn_spo_allocation_links.py`, which is unchanged.

Revision ID: 324_grn_line_spo_number_raw
Revises: 322_merge_dealer_kit_customers
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "324_grn_line_spo_number_raw"
down_revision = "322_merge_dealer_kit_customers"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_picking_lines_spo_number_raw_key"

# The import's `_GRN_SPO_SEPARATORS` (`[,;\n\r]+|\s{2,}`) as a Postgres regex: a
# header matching it names MORE THAN ONE SPO, and only a single-SPO header can
# state what one of its lines was received against.
_MULTI_SPO_HEADER = r"[,;\r\n]|\s{2,}"


def _backfill() -> None:
    """Set the stated SPO on rows that predate the column.

    Guarded `WHERE spo_number_raw IS NULL` rather than the "set where mismatch"
    form PRINCIPLES prefers: at migration time every row is NULL, so the two are
    identical here, and on any RE-RUN a value written by a later import is more
    authoritative than one re-derived from the header and must not be clobbered.
    """
    # A linked line's own allocation is the strongest evidence of what it was
    # received against, so it wins over the header (which may name a different SPO).
    op.execute(
        """
        UPDATE picking_lines AS pl
           SET spo_number_raw = alloc.spo_number
          FROM spo_allocations AS alloc
         WHERE pl.spo_allocation_id = alloc.id
           AND pl.spo_number_raw IS NULL
           AND alloc.spo_number IS NOT NULL
           AND btrim(alloc.spo_number) <> ''
        """
    )
    # An unlinked line takes its GRN header's SPO, but ONLY when that header names
    # exactly one - the same scalar rule the import applies.
    op.execute(
        f"""
        UPDATE picking_lines AS pl
           SET spo_number_raw = btrim(ph.spo_number)
          FROM picking_headers AS ph
         WHERE pl.picking_header_id = ph.id
           AND pl.spo_allocation_id IS NULL
           AND pl.spo_number_raw IS NULL
           AND ph.picking_type = 'goods_received'
           AND ph.spo_number IS NOT NULL
           AND btrim(ph.spo_number) <> ''
           AND btrim(ph.spo_number) !~ '{_MULTI_SPO_HEADER}'
        """
    )


def upgrade() -> None:
    op.add_column(
        "picking_lines",
        sa.Column("spo_number_raw", sa.String(length=255), nullable=True),
    )
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON picking_lines "
        "(upper(regexp_replace(spo_number_raw, '[^A-Za-z0-9]', '', 'g'))) "
        "WHERE spo_allocation_id IS NULL"
    )
    _backfill()


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    op.drop_column("picking_lines", "spo_number_raw")
