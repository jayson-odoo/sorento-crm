""""Supplied with" companion rules: two new tables, two new columns.

Revision ID: 495_product_companion_rules
Revises: 494_from_so_external_link

PLAN-scm-supplied-with-companions.md section 3.1/3.2. `product_companion_rules` names a
COMPANION product (CKSW015), a supplier scope (nullable - NULL means "any supplier",
ruling 3) and a ratio (companion units per one host unit, ruling 1). Each rule holds one
or more `product_companion_rule_hosts` - two for the pair case (SC-RL needs both X and
Y present), one for the common case.

`bundled_qty` / `bundled_with_row_id` on `projects.order_inquiry_rows` are the derived
half - never typed, the one writer is `ProjectOrderInquiryService.derive_bundles` (S5).

Two partial unique indexes stand in for the natural key `(company_id,
companion_product_id, supplier_id)`: Postgres treats every NULL as distinct, so a plain
UNIQUE constraint would let two "any supplier" rules coexist for the same companion
(UAC A4's second case). RESTRICT on both `companion_product_id` and `host_product_id` -
a product named on an active rule cannot be deleted out from under it (UAC A6).
"""
import sqlalchemy as sa
from alembic import op

revision = "495_product_companion_rules"
down_revision = "494_from_so_external_link"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS product_companion_rules (
                id UUID PRIMARY KEY,
                company_id UUID NOT NULL REFERENCES companies(id),
                companion_product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
                ratio NUMERIC(15,4) NOT NULL DEFAULT 1,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now(),
                created_by UUID
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_product_companion_rules_companion "
            "ON product_companion_rules (companion_product_id)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_product_companion_rules_supplier "
            "ON product_companion_rules (company_id, companion_product_id, supplier_id) "
            "WHERE supplier_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_product_companion_rules_any_supplier "
            "ON product_companion_rules (company_id, companion_product_id) "
            "WHERE supplier_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE SEQUENCE IF NOT EXISTS product_companion_rule_host_seq
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS product_companion_rule_hosts (
                id UUID PRIMARY KEY,
                rule_id UUID NOT NULL REFERENCES product_companion_rules(id) ON DELETE CASCADE,
                host_product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                seq BIGINT NOT NULL DEFAULT nextval('product_companion_rule_host_seq'),
                created_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "ALTER SEQUENCE product_companion_rule_host_seq OWNED BY "
            "product_companion_rule_hosts.seq"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_product_companion_rule_host "
            "ON product_companion_rule_hosts (rule_id, host_product_id)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_product_companion_rule_hosts_rule_id "
            "ON product_companion_rule_hosts (rule_id)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_product_companion_rule_hosts_host_product_id "
            "ON product_companion_rule_hosts (host_product_id)"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.order_inquiry_rows "
            "ADD COLUMN IF NOT EXISTS bundled_qty NUMERIC(15,4) NOT NULL DEFAULT 0"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.order_inquiry_rows "
            "ADD COLUMN IF NOT EXISTS bundled_with_row_id UUID "
            "REFERENCES projects.order_inquiry_rows(id) ON DELETE SET NULL"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_project_order_inquiry_rows_bundled_with "
            "ON projects.order_inquiry_rows (bundled_with_row_id)"
        )
    )


def revert(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE projects.order_inquiry_rows DROP COLUMN IF EXISTS bundled_with_row_id"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE projects.order_inquiry_rows DROP COLUMN IF EXISTS bundled_qty"
        )
    )
    bind.execute(sa.text("DROP TABLE IF EXISTS product_companion_rule_hosts"))
    bind.execute(sa.text("DROP SEQUENCE IF EXISTS product_companion_rule_host_seq"))
    bind.execute(sa.text("DROP TABLE IF EXISTS product_companion_rules"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
