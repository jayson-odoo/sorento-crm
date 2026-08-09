"""Give the four spec tables a uuid `id`, per ADR-PRODUCT-STANDARDS §Data Model.

They shipped keyed on their natural keys - `spec_key`, `policy_key`, `product_code`,
`product_id` - which reads fine in isolation but breaks a repo-wide invariant: the
polymorphic key columns (`audit_logs.entity_id`, `notifications.source_entity_id`, …)
can only be typed uuid if every id they might hold is one. A single natural-key table
forces those columns back to text, and text accepts a `uuid = text` mismatch that
Postgres would otherwise reject at write time.

The natural key is not lost, it stops being the primary key: each becomes UNIQUE NOT
NULL, so every existing lookup and upsert path keeps working unchanged.

Revision ID: 311m_spec_tables_uuid_id
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "311m_spec_tables_uuid_id"
down_revision = "311l_spec_suppressed_values"
branch_labels = None
depends_on = None


# (table, natural key column, name for the unique constraint that replaces the PK)
_TABLES = [
    ("product_spec_registry", "spec_key", "uq_product_spec_registry_spec_key"),
    ("product_spec_search_policy", "policy_key", "uq_product_spec_search_policy_key"),
    ("product_flyer_text", "product_code", "uq_product_flyer_text_product_code"),
    ("product_specifications", "product_id", "uq_product_specifications_product_id"),
]


def upgrade() -> None:
    for table, natural_key, unique_name in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=False),
                nullable=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
        )
        # Rows already present predate the default, so fill them explicitly.
        op.execute(f"UPDATE {table} SET id = gen_random_uuid() WHERE id IS NULL")
        op.alter_column(table, "id", nullable=False)
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, ["id"])
        op.create_unique_constraint(unique_name, table, [natural_key])


def downgrade() -> None:
    for table, natural_key, unique_name in _TABLES:
        op.drop_constraint(unique_name, table, type_="unique")
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, [natural_key])
        op.drop_column(table, "id")
