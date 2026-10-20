"""SPEC-REGISTRY-UI: the chatbot meaning of a spec field and the owned-label flag.

`parser_hint` is one line the parser sees on the field's `{{specs}}` line; `label_owned`
stops `seed_spec_registry` reverting a name staff edited. Additive and idempotent
(`IF NOT EXISTS`) so the shared dev DB, which converges through `create_all`, can take it
in any order.

Plan: documentation/plans/chatbot/PLAN-spec-registry-ui-17oct.md.

Revision ID: spec_hint_0001
Revises: fin_0003_billing_outstanding
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "spec_hint_0001"
down_revision = "fin_0003_billing_outstanding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE product_spec_registry ADD COLUMN IF NOT EXISTS parser_hint text NULL")
    op.execute(
        "ALTER TABLE product_spec_registry "
        "ADD COLUMN IF NOT EXISTS label_owned boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE product_spec_registry DROP COLUMN IF EXISTS label_owned")
    op.execute("ALTER TABLE product_spec_registry DROP COLUMN IF EXISTS parser_hint")
