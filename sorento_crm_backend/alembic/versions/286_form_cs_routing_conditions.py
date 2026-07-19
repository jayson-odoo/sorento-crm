"""CS routing predicate engine + sales_type lookup + binding default_value.

Revision ID: 286_form_cs_routing_conditions
Revises: 271_audit_action_allow_import

R2 (documentation/plans/forms/PLAN-form-cs-routing-conditions.md). Additive +
backward-safe:

1. lookup_bindings.default_value  — generic: a binding may declare a default option
   the FE pre-selects on new forms.
2. purchase_requests.sales_type   — new PR field (project / cash_sales), lookup-bound.
3. lookup set procurement_sales_type + options (+ binding, default_value='project').
4. respond_contact_cs_routing.match_conditions (JSONB) + priority (INT) — the generic
   predicate routing engine. Old unique (contact, use_case) → expression unique
   (contact, use_case, md5(match_conditions::text)) so one pin per distinct
   condition-set. Existing rows default to '[]' (wildcard) = identical behaviour.

NOTE (merge): chained onto the worktree head 271. The isolated test DB is stamped
to 271 first (the local DB sat at 285 from an unmerged SCM branch). At real merge,
re-chain down_revision onto the then-current main head + renumber.

Idempotent, reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "286_form_cs_routing_conditions"
down_revision = "285_market_signal_sources"
branch_labels = None
depends_on = None

SET_KEY = "procurement_sales_type"
OPTIONS = (
    ("project", "Project", 10),
    ("cash_sales", "Cash Sales", 20),
)
KEYWORDS = {
    "cash_sales": ["cash", "cash sale", "cash sales"],
    "project": ["project", "project sales"],
}
DEFAULT_VALUE = "project"


def _set_id_subquery() -> str:
    return (
        "SELECT id FROM lookup_sets "
        f"WHERE tenant_id IS NULL AND set_key = '{SET_KEY}' "
        "ORDER BY created_at ASC, id ASC LIMIT 1"
    )


def upgrade() -> None:
    # 1. Generic: default option on a binding (nullable; validated app-side ∈ set).
    op.add_column(
        "lookup_bindings",
        sa.Column("default_value", sa.String(length=150), nullable=True),
    )

    # 2. New PR field.
    op.add_column(
        "purchase_requests",
        sa.Column("sales_type", sa.String(length=50), nullable=True),
    )

    # 3. Lookup set + options + keywords.
    op.execute(
        sa.text(
            f"""
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT gen_random_uuid(), NULL, '{SET_KEY}',
                   'Procurement - Sales Type',
                   'Purchase request sales type (Project / Cash Sales). Routes CS assignment.',
                   TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_sets WHERE tenant_id IS NULL AND set_key = '{SET_KEY}'
            )
            """
        )
    )
    for value, label, sort_order in OPTIONS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
                SELECT gen_random_uuid(), s.id, :value, :label, :sort_order, TRUE
                FROM ({_set_id_subquery()}) s
                ON CONFLICT (set_id, lower(value)) DO UPDATE
                SET label = EXCLUDED.label, sort_order = EXCLUDED.sort_order,
                    is_active = TRUE, updated_at = now()
                """
            ).bindparams(value=value, label=label, sort_order=sort_order)
        )
    for value, kw_list in KEYWORDS.items():
        for kw in kw_list:
            op.execute(
                sa.text(
                    f"""
                    INSERT INTO lookup_option_keywords (id, option_id, keyword, locale)
                    SELECT gen_random_uuid(), o.id, :kw, NULL
                    FROM lookup_options o
                    WHERE o.set_id = ({_set_id_subquery()}) AND lower(o.value) = :value
                    ON CONFLICT (option_id, keyword, locale) DO NOTHING
                    """
                ).bindparams(kw=kw, value=value)
            )

    # 3b. Binding LAST (validates existing column values; all NULL → passes),
    #     carrying the default_value the FE pre-selects.
    op.execute(
        sa.text(
            f"""
            INSERT INTO lookup_bindings
                (id, tenant_id, set_id, table_name, column_name, default_value)
            SELECT gen_random_uuid(), NULL, s.id, 'purchase_requests', 'sales_type', :dflt
            FROM ({_set_id_subquery()}) s
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_bindings b
                WHERE b.tenant_id IS NULL
                  AND b.table_name = 'purchase_requests' AND b.column_name = 'sales_type'
            )
            """
        ).bindparams(dflt=DEFAULT_VALUE)
    )

    # 4. Predicate engine columns on the CS pin table.
    op.add_column(
        "respond_contact_cs_routing",
        sa.Column(
            "match_conditions",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "respond_contact_cs_routing",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    # existing rows -> explicit wildcard (defensive; server_default already covers).
    op.execute("UPDATE respond_contact_cs_routing SET match_conditions = '[]'::jsonb "
               "WHERE match_conditions IS NULL")

    # 4b. Swap unique: (contact, use_case) -> (contact, use_case, md5(conditions)).
    op.execute("ALTER TABLE respond_contact_cs_routing "
               "DROP CONSTRAINT IF EXISTS uq_cs_routing_contact_use_case")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cs_routing_contact_use_case_conditions "
        "ON respond_contact_cs_routing "
        "(respond_contact_id, use_case, md5(match_conditions::text))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_cs_routing_contact_use_case_conditions")
    op.execute(
        "ALTER TABLE respond_contact_cs_routing "
        "ADD CONSTRAINT uq_cs_routing_contact_use_case "
        "UNIQUE (respond_contact_id, use_case)"
    )
    op.drop_column("respond_contact_cs_routing", "priority")
    op.drop_column("respond_contact_cs_routing", "match_conditions")

    op.execute(
        "DELETE FROM lookup_bindings WHERE tenant_id IS NULL "
        "AND table_name = 'purchase_requests' AND column_name = 'sales_type'"
    )
    op.execute(
        f"DELETE FROM lookup_option_keywords WHERE option_id IN "
        f"(SELECT id FROM lookup_options WHERE set_id = ({_set_id_subquery()}))"
    )
    op.execute(f"DELETE FROM lookup_options WHERE set_id = ({_set_id_subquery()})")
    op.execute(f"DELETE FROM lookup_sets WHERE tenant_id IS NULL AND set_key = '{SET_KEY}'")

    op.drop_column("purchase_requests", "sales_type")
    op.drop_column("lookup_bindings", "default_value")
