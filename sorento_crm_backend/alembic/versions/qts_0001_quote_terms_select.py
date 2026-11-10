"""QUOTE-TERMS-SELECT: the AutoCount `payment_terms` master, the picked term and the validity pair
on the terms template and the quotation, and the `master_data.payment_terms.*` slugs.

Revision ID: qts_0001_quote_terms_select
Revises: ptag_0021_icon_conditions
Create Date: 2026-11-10

`payment_terms` is AutoCount `Terms` (DisplayTerm = term_code, Terms = term_rule), company-scoped, unique on
(company_id, term_code), written only by the ESB ingest (contract 2.14). It starts empty, so no
legacy payment-terms text can map here; the ingest links exact matches when terms arrive.

`projects.quotation_templates` and `projects.quotation_documents` gain `payment_term_id` (SET
NULL), `validity_value`, `validity_unit`. Their `payment_terms` / `validity` text columns stay the
printed text, so nothing already stored or issued changes. Legacy validity text that is exactly a
number and a unit ("30 days", "2 Weeks") backfills the pair; everything else stays text only.

`customers.payment_terms_code` holds AutoCount `Debtor.DisplayTerm` from the customer feed (owner
Q3): a new quotation for that customer defaults to the synced term of that code.

Grants: every role holding `master_data.item_classes.<action>` gets
`master_data.payment_terms.<action>` (the item_class_0001 shape: rows created when absent). Additive,
every statement idempotent; downgrade drops the schema objects and leaves the grants.
"""
import sqlalchemy as sa
from alembic import op

revision = "qts_0001_quote_terms_select"
down_revision = "ptag_0021_icon_conditions"
branch_labels = None
depends_on = None

_ACTIONS = (("view", "View"), ("edit", "Edit"), ("delete", "Delete"))
_TABLES = ("projects.quotation_templates", "projects.quotation_documents")
_VALIDITY_RE = r"^\s*([0-9]{1,3})\s*(day|week|month|year)s?\s*$"


def apply_grants(bind) -> None:
    for action, verb in _ACTIONS:
        slug = f"master_data.payment_terms.{action}"
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": f"{verb} Payment Terms", "descr": f"Permission to {action} Payment Terms."},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT gen_random_uuid()::text, rp.role_id, target.id, now()
                FROM user_role_permissions rp
                JOIN user_permissions source ON source.id = rp.permission_id AND source.slug = :source
                CROSS JOIN user_permissions target
                WHERE target.slug = :slug
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"source": f"master_data.item_classes.{action}", "slug": slug},
        )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_terms (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES companies(id),
            term_code VARCHAR(100) NOT NULL,
            term_rule TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_terms_company_id ON payment_terms (company_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_terms_company_term_code "
        "ON payment_terms (company_id, term_code)"
    )
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS payment_term_id UUID "
            "REFERENCES payment_terms(id) ON DELETE SET NULL"
        )
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS validity_value INTEGER")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS validity_unit VARCHAR(8)")
        # Exact number + unit only; the text itself is left as it is.
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET validity_value = (regexp_match(validity, :re, 'i'))[1]::int,
                    validity_unit = lower((regexp_match(validity, :re, 'i'))[2])
                WHERE validity_value IS NULL
                  AND validity ~* :re
                  AND (regexp_match(validity, :re, 'i'))[1]::int BETWEEN 1 AND 999
                """
            ).bindparams(re=_VALIDITY_RE)
        )
    # Owner Q3: AutoCount Debtor.DisplayTerm on the customer feed again (contract 2.14), the
    # default payment term of a new quotation for that customer.
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS payment_terms_code VARCHAR(100)")
    apply_grants(op.get_bind())


def downgrade() -> None:
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS payment_terms_code")
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS validity_unit")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS validity_value")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS payment_term_id")
    op.execute("DROP TABLE IF EXISTS payment_terms")
