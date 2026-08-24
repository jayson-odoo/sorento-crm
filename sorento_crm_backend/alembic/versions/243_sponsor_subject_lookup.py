"""Sponsor subject lookup set + sponsor_subject_other column + backfill.

Revision ID: 243_sponsor_subject_lookup
Revises: c1d2e3f4a5b6
Create Date: 2026-06-24

Sponsorship forms: "purpose" IS the sponsor subject. This migration collapses the
two into a strict lookup on ``purchase_requests.sponsor_subject`` and parks any
unmatched free text in a new ``sponsor_subject_other`` column.

Ordering (matters - the binding validates all existing values when it attaches):
1. Create lookup set ``procurement_sponsor_subject`` + options + keywords.
2. Add nullable ``purchase_requests.sponsor_subject_other``.
3. Backfill every sponsorship row (purpose wins, fallback old sponsor_subject):
   keyword-match → showroom / mockup; else ``others`` + park raw text in other.
4. Create the binding LAST so every sponsorship value is already valid.

Idempotent, JOIN-based, reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "243_sponsor_subject_lookup"
down_revision = "242_seed_takeover"
branch_labels = None
depends_on = None


SET_KEY = "procurement_sponsor_subject"

# (value, label, sort_order)
OPTIONS = (
    ("showroom", "Showroom", 10),
    ("mockup", "Mockup", 20),
    ("others", "Others", 30),
)

# value -> list of keyword synonyms (matched case-insensitively against the
# source text during backfill and at runtime by the lookup resolver).
KEYWORDS = {
    "showroom": ["showroom", "show room"],
    "mockup": ["mockup", "mock up", "mock-up", "sample", "prototype"],
}


def _set_id_subquery() -> str:
    return (
        "SELECT id FROM lookup_sets "
        f"WHERE tenant_id IS NULL AND set_key = '{SET_KEY}' "
        "ORDER BY created_at ASC, id ASC LIMIT 1"
    )


def upgrade() -> None:
    # 1. Lookup set
    op.execute(
        sa.text(
            f"""
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT gen_random_uuid(), NULL, '{SET_KEY}',
                   'Procurement - Sponsor Subject',
                   'Sponsorship form sponsor subject values (Showroom / Mockup / Others).',
                   TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_sets
                WHERE tenant_id IS NULL AND set_key = '{SET_KEY}'
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE lookup_sets
            SET name = 'Procurement - Sponsor Subject',
                description = 'Sponsorship form sponsor subject values (Showroom / Mockup / Others).',
                is_active = TRUE,
                updated_at = now()
            WHERE tenant_id IS NULL AND set_key = '{SET_KEY}'
            """
        )
    )

    # 1b. Options
    for value, label, sort_order in OPTIONS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
                SELECT gen_random_uuid(), s.id, :value, :label, :sort_order, TRUE
                FROM ({_set_id_subquery()}) s
                ON CONFLICT (set_id, lower(value)) DO UPDATE
                SET label = EXCLUDED.label,
                    sort_order = EXCLUDED.sort_order,
                    is_active = TRUE,
                    updated_at = now()
                """
            ).bindparams(value=value, label=label, sort_order=sort_order)
        )

    # 1c. Keywords (synonyms)
    for value, kw_list in KEYWORDS.items():
        for kw in kw_list:
            op.execute(
                sa.text(
                    f"""
                    INSERT INTO lookup_option_keywords (id, option_id, keyword, locale)
                    SELECT gen_random_uuid(), o.id, :kw, NULL
                    FROM lookup_options o
                    WHERE o.set_id = ({_set_id_subquery()})
                      AND lower(o.value) = :value
                    ON CONFLICT (option_id, keyword, locale) DO NOTHING
                    """
                ).bindparams(kw=kw, value=value)
            )

    # 2. New column
    op.add_column(
        "purchase_requests",
        sa.Column("sponsor_subject_other", sa.Text(), nullable=True),
    )

    # 3. Backfill sponsorship rows. Source = purpose if non-empty else sponsor_subject.
    #    a) Showroom keyword match.
    op.execute(
        sa.text(
            """
            UPDATE purchase_requests pr
            SET sponsor_subject = 'showroom',
                sponsor_subject_other = NULL
            WHERE pr.request_type = 'sponsorship_form'
              AND lower(coalesce(nullif(btrim(pr.purpose), ''), coalesce(pr.sponsor_subject, '')))
                  ~ '(showroom|show room)'
            """
        )
    )
    #    b) Mockup keyword match (only rows not already set to showroom by (a)).
    op.execute(
        sa.text(
            """
            UPDATE purchase_requests pr
            SET sponsor_subject = 'mockup',
                sponsor_subject_other = NULL
            WHERE pr.request_type = 'sponsorship_form'
              AND coalesce(pr.sponsor_subject, '') <> 'showroom'
              AND lower(coalesce(nullif(btrim(pr.purpose), ''), coalesce(pr.sponsor_subject, '')))
                  ~ '(mockup|mock up|mock-up|sample|prototype)'
            """
        )
    )
    #    c) Everything else → others, park the raw source text (when present).
    op.execute(
        sa.text(
            """
            UPDATE purchase_requests pr
            SET sponsor_subject_other =
                    nullif(btrim(coalesce(nullif(btrim(pr.purpose), ''), coalesce(pr.sponsor_subject, ''))), ''),
                sponsor_subject = 'others'
            WHERE pr.request_type = 'sponsorship_form'
              AND coalesce(pr.sponsor_subject, '') NOT IN ('showroom', 'mockup', 'others')
            """
        )
    )

    # 4. Binding LAST (validates that all sponsorship values are now options).
    op.execute(
        sa.text(
            f"""
            UPDATE lookup_bindings b
            SET set_id = s.id, updated_at = now()
            FROM ({_set_id_subquery()}) s
            WHERE b.tenant_id IS NULL
              AND b.table_name = 'purchase_requests'
              AND b.column_name = 'sponsor_subject'
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO lookup_bindings (id, tenant_id, set_id, table_name, column_name)
            SELECT gen_random_uuid(), NULL, s.id, 'purchase_requests', 'sponsor_subject'
            FROM ({_set_id_subquery()}) s
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_bindings b
                WHERE b.tenant_id IS NULL
                  AND b.table_name = 'purchase_requests'
                  AND b.column_name = 'sponsor_subject'
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            DELETE FROM lookup_bindings
            WHERE tenant_id IS NULL
              AND table_name = 'purchase_requests'
              AND column_name = 'sponsor_subject'
              AND set_id IN (
                  SELECT id FROM lookup_sets
                  WHERE tenant_id IS NULL AND set_key = '{SET_KEY}'
              )
            """
        )
    )
    op.drop_column("purchase_requests", "sponsor_subject_other")
    # Cascades to options + keywords via FK ondelete=CASCADE.
    op.execute(
        sa.text(
            f"""
            DELETE FROM lookup_sets
            WHERE tenant_id IS NULL AND set_key = '{SET_KEY}'
            """
        )
    )
