"""Saved decisions on the planning board: projects.so_supply_decision_drafts.

S4 of `PLAN-scm-fulfilment-feedback-2sep.md`, ruling R-F, and its "Deviation (3 Sep)" note:
a draft is its OWN row rather than a `draft` state on `so_supply_decisions`, which is one
row per ORDER REVISION with `revision_no` and `line_snapshots` NOT NULL and a partial unique
index enforcing one active revision per order.

Keyed by the board's own contribution key. `sales_order_id` is the CORE sales order, which
is what `_Row.key` carries - the board is built from the core book and a line whose order
nobody has adopted yet can still be saved. The unique index is the first THREE parts of that
key: `bucket_key` is derived from the board's granularity as well as the line's date, so a
uniqueness rule including it would lose every saved line the moment the planner switched
between week and day.

Hand-written and guarded, for the reason 443/450/452/460 state: the shared dev database is a
prod copy whose `alembic_version` points at another lane's head, so this is applied there by
hand and re-running it has to be a no-op rather than a failure.

Revision ID: 461_so_supply_decision_drafts
Revises: 460_fulfilment_immediate_share
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "461_so_supply_decision_drafts"
down_revision = "460_fulfilment_immediate_share"
branch_labels = None
depends_on = None

TABLE = "so_supply_decision_drafts"
SCHEMA = "projects"


def _tables(schema: str) -> set:
    return set(sa.inspect(op.get_bind()).get_table_names(schema=schema))


def upgrade() -> None:
    if TABLE in _tables(SCHEMA):
        return
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("sales_order_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(length=100), nullable=False),
        sa.Column("bucket_key", sa.String(length=32), nullable=False),
        sa.Column("decision", postgresql.JSONB(), nullable=False),
        # `line_snapshot`, not `proposed_snapshot` (S1, code review round 3): staleness is
        # judged on the LINE's own facts (open qty, required date), not on a proposal that
        # depends on which orders share the board. Renamed by hand on the dev DB (the table
        # there was hand-created too): `ALTER TABLE projects.so_supply_decision_drafts
        # RENAME COLUMN proposed_snapshot TO line_snapshot;`.
        sa.Column("line_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("saved_by", sa.String(length=100), nullable=True),
        sa.Column(
            "saved_at", sa.DateTime(timezone=False), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(
            ["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["saved_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "company_id",
            "sales_order_id",
            "line_no",
            "item_code",
            name="uq_so_supply_decision_drafts_line",
        ),
        schema=SCHEMA,
    )
    # `ix_projects_..._company_id`, matching what `CompanyScopedMixin`'s `index=True`
    # generates under `create_all` (N1, code review round 3 - see e.g.
    # `ix_projects_planning_change_batches_company_id` in `29d85dc3ccc3`), not the
    # unprefixed name this migration first shipped with. Renamed by hand on the dev DB too:
    # `ALTER INDEX projects.ix_so_supply_decision_drafts_company_id RENAME TO
    # ix_projects_so_supply_decision_drafts_company_id;`.
    op.create_index(
        "ix_projects_so_supply_decision_drafts_company_id",
        TABLE,
        ["company_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_so_supply_decision_drafts_order",
        TABLE,
        ["sales_order_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    if TABLE not in _tables(SCHEMA):
        return
    op.drop_index("ix_so_supply_decision_drafts_order", TABLE, schema=SCHEMA)
    op.drop_index(
        "ix_projects_so_supply_decision_drafts_company_id", TABLE, schema=SCHEMA
    )
    op.drop_table(TABLE, schema=SCHEMA)
