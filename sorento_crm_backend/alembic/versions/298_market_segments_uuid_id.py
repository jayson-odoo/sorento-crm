"""Give market_segments a uuid surrogate `id`, keep `code` as a unique key.

Design principle (documentation/PRINCIPLES.md, enforced by
tests/test_schema_uuid_id_principle.py): every domain table has a uuid `id`
primary key. market_segments was the one natural-key holdout — PK on `code`
('retail' / 'project').

`code` is a human-facing business key referenced by three tables
(customers.market_segment_code, respond_contact_market_segments.segment_code,
team_member_market_segments.segment_code), so it stays as a UNIQUE NOT NULL
column and those FKs keep pointing at it. Only the PK moves to the new `id`.

Sequence matters: the three FKs currently depend on the `code` primary-key
index, so Postgres refuses to drop that PK while they exist. We give `code` its
own unique constraint, drop the FKs, swap the PK, then re-create the FKs against
`code`'s unique constraint. Two rows, so the rewrite is trivial.

Revision ID: 298_market_segments_uuid_id
Revises: 298_merge_main_into_remove_mcp
"""
from alembic import op

revision = "298_market_segments_uuid_id"
# Chains onto the merge head that #30 landed on main (which unified main's
# chat-state-trace with the remove-mcp chain), not the raw 297, so this branch
# keeps a single linear alembic head after main is merged in.
down_revision = "298_merge_main_into_remove_mcp"
branch_labels = None
depends_on = None


_FKS = [
    ("customers", "customers_market_segment_code_fkey", "market_segment_code"),
    (
        "respond_contact_market_segments",
        "respond_contact_market_segments_segment_code_fkey",
        "segment_code",
    ),
    (
        "team_member_market_segments",
        "team_member_market_segments_segment_code_fkey",
        "segment_code",
    ),
]


def upgrade():
    # 1. Surrogate id, backfilled for the existing rows by the default.
    op.execute(
        "ALTER TABLE market_segments "
        "ADD COLUMN id uuid NOT NULL DEFAULT gen_random_uuid()"
    )
    # 2. Independent unique constraint on code so the FKs have a target once the
    #    PK moves off it.
    op.execute(
        "ALTER TABLE market_segments "
        "ADD CONSTRAINT uq_market_segments_code UNIQUE (code)"
    )
    # 3. Drop the FKs that ride the old code PK.
    for table, fk, _col in _FKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {fk}")
    # 4. Swap the primary key onto id.
    op.execute("ALTER TABLE market_segments DROP CONSTRAINT market_segments_pkey")
    op.execute("ALTER TABLE market_segments ADD PRIMARY KEY (id)")
    # 5. Re-create the FKs, now against code's unique constraint.
    for table, fk, col in _FKS:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {fk} "
            f"FOREIGN KEY ({col}) REFERENCES market_segments (code)"
        )


def downgrade():
    for table, fk, _col in _FKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {fk}")
    op.execute("ALTER TABLE market_segments DROP CONSTRAINT market_segments_pkey")
    op.execute("ALTER TABLE market_segments ADD PRIMARY KEY (code)")
    op.execute(
        "ALTER TABLE market_segments DROP CONSTRAINT uq_market_segments_code"
    )
    op.execute("ALTER TABLE market_segments DROP COLUMN id")
    for table, fk, col in _FKS:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {fk} "
            f"FOREIGN KEY ({col}) REFERENCES market_segments (code)"
        )
