"""PROJECT-REG-PORTAL: portal project registrations, the profile's state and mukim, the two
lookup sets the form reads, the approve permission and the PPF project numbering rule.

Additive and idempotent (`IF NOT EXISTS`, `WHERE NOT EXISTS`, `ON CONFLICT`) so the shared dev
DB, which converges through `create_all`, can take it in any order.

- `projects.project_registrations` (D3) and `projects.sales_profile.state` / `.mukim` (D12).
- Lookup sets `project_building_type` and `my_state`, seeded; client-editable afterwards.
- Permission `projects.registrations.approve` (D10), granted to the admin roles and to the
  existing roles named in `APPROVER_ROLE_NAMES` (case-insensitive name match).
- Project numbering becomes `PPF{yy}{mm}`, 3 digits, monthly (D6), ONLY while the rule still
  holds the shipped default `PRJ-`; a customised rule is left alone. Existing codes are
  untouched.

Plan: documentation/plans/projects/PLAN-project-registration-portal-25oct.md.

Revision ID: prreg_0001_project_registrations
Revises: oihr_0010_so_remark_column
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "prreg_0001_project_registrations"
down_revision = "oihr_0010_so_remark_column"
branch_labels = None
depends_on = None

PERMISSION = (
    "projects.registrations.approve",
    "Approve Project Registrations",
    "Review, approve or reject project registrations raised from the portal.",
)
_ADMIN_ROLES = ("superadmin", "admin")

# The existing roles that approve project registrations besides the admin roles (owner ruling,
# 25 Oct 16:35: both). A name with no matching role grants nothing extra.
APPROVER_ROLE_NAMES = ("Project Sales Manager", "Project Sales Coordinator")

BUILDING_TYPES = (
    "Residential landed",
    "Residential high-rise",
    "Commercial",
    "Mixed development",
    "Factory / industrial",
    "Hotel",
    "Hospital",
    "School / institutional",
    "Government building",
    "Renovation",
)
STATES = (
    "Johor",
    "Kedah",
    "Kelantan",
    "Melaka",
    "Negeri Sembilan",
    "Pahang",
    "Perak",
    "Perlis",
    "Pulau Pinang",
    "Sabah",
    "Sarawak",
    "Selangor",
    "Terengganu",
    "Kuala Lumpur",
    "Labuan",
    "Putrajaya",
)
LOOKUP_SETS = (
    ("project_building_type", "Project - Type of building", BUILDING_TYPES),
    ("my_state", "Malaysia - State", STATES),
)


def _schema(bind, module: str) -> str:
    """Where a module's tables live, for RAW SQL, under BOTH substrates (see
    `sds_0001_stock_debt_snapshots`)."""
    current = bind.exec_driver_sql("SELECT current_schema()").scalar()
    return module if current in (None, "public") else f"{current}_{module}"


def _seed_lookup(bind, set_key: str, name: str, labels) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT gen_random_uuid(), NULL, :k, :n, NULL, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :k
            )
            """
        ),
        {"k": set_key, "n": name},
    )
    for order, label in enumerate(labels, start=1):
        bind.execute(
            sa.text(
                """
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
                SELECT gen_random_uuid(), s.id, :v, :v, :o, TRUE
                  FROM lookup_sets s
                 WHERE s.tenant_id IS NULL AND s.set_key = :k
                ON CONFLICT (set_id, lower(value)) DO NOTHING
                """
            ),
            {"k": set_key, "v": label, "o": order * 10},
        )


def upgrade() -> None:
    bind = op.get_bind()
    p = _schema(bind, "projects")
    for statement in (
        f'CREATE SCHEMA IF NOT EXISTS "{p}"',
        f"""
        CREATE TABLE IF NOT EXISTS "{p}".project_registrations (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES public.companies(id),
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            contact_id TEXT REFERENCES public.respond_contacts(id) ON DELETE SET NULL,
            sales_agent_id UUID REFERENCES public.sales_agents(id) ON DELETE SET NULL,
            applicant_user_id VARCHAR(100) REFERENCES public.users(id) ON DELETE SET NULL,
            project_id UUID REFERENCES "{p}".projects(id) ON DELETE SET NULL,
            submitted_at TIMESTAMP,
            decided_at TIMESTAMP,
            decided_by VARCHAR(100) REFERENCES public.users(id) ON DELETE SET NULL,
            reject_reason TEXT,
            title TEXT,
            distributor_name VARCHAR(255),
            customer_id UUID REFERENCES public.customers(id) ON DELETE SET NULL,
            customer_name VARCHAR(255),
            type_of_building VARCHAR(255),
            state VARCHAR(100),
            mukim VARCHAR(255),
            your_ref VARCHAR(255),
            developer_name VARCHAR(255),
            main_contractor_name VARCHAR(255),
            architect_name VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """,
        f'CREATE INDEX IF NOT EXISTS ix_projects_project_registrations_company_id ON "{p}".project_registrations (company_id)',
        f'CREATE INDEX IF NOT EXISTS ix_project_registrations_status ON "{p}".project_registrations (status)',
        f'CREATE INDEX IF NOT EXISTS ix_project_registrations_contact ON "{p}".project_registrations (contact_id)',
        f'ALTER TABLE "{p}".sales_profile ADD COLUMN IF NOT EXISTS state VARCHAR(100)',
        f'ALTER TABLE "{p}".sales_profile ADD COLUMN IF NOT EXISTS mukim VARCHAR(255)',
    ):
        bind.execute(sa.text(statement))

    for set_key, name, labels in LOOKUP_SETS:
        _seed_lookup(bind, set_key, name, labels)

    slug, name, descr = PERMISSION
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": slug, "name": name, "descr": descr},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, tgt.id, now()
              FROM user_roles r
             CROSS JOIN user_permissions tgt
             WHERE (r.slug = ANY(:roles) OR lower(btrim(r.name)) = ANY(:approvers))
               AND tgt.slug = :slug
               AND NOT EXISTS (
                   SELECT 1 FROM user_role_permissions existing
                    WHERE existing.role_id = r.id
                      AND existing.permission_id = tgt.id
               )
            """
        ),
        {
            "slug": slug,
            "roles": list(_ADMIN_ROLES),
            "approvers": [n.strip().lower() for n in APPROVER_ROLE_NAMES],
        },
    )

    # Only the shipped default is replaced; the first draw of a monthly rule restarts at
    # start_value on its own (no last_reset_key yet).
    bind.execute(
        sa.text(
            """
            UPDATE document_numbering_rules
               SET prefix_template = 'PPF{yy}{mm}', number_digits = 3, reset_policy = 'monthly'
             WHERE doc_type = 'project' AND prefix_template = 'PRJ-'
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    p = _schema(bind, "projects")
    slug = PERMISSION[0]
    # Put the project rule back on the shipped default, but ONLY where it is still exactly the
    # shape the upgrade wrote: a PPF rule someone has changed since is their choice.
    # The counter moves with it: the PPF draws reset it, and the next PRJ code must land
    # past every PRJ code that already exists, or the rollback hands out a duplicate.
    bind.execute(
        sa.text(
            f"""
            UPDATE document_numbering_rules
               SET prefix_template = 'PRJ-', number_digits = 6, reset_policy = 'none',
                   last_reset_key = NULL,
                   next_value = GREATEST(
                       next_value,
                       COALESCE(
                           (SELECT MAX(substring(project_code from '^PRJ-([0-9]+)$')::int)
                              FROM "{p}".projects
                             WHERE project_code ~ '^PRJ-[0-9]+$'),
                           0
                       ) + 1
                   )
             WHERE doc_type = 'project' AND prefix_template = 'PPF{{yy}}{{mm}}'
               AND number_digits = 3 AND reset_policy = 'monthly'
            """
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :slug)"
        ),
        {"slug": slug},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug})
    bind.execute(sa.text(f'ALTER TABLE "{p}".sales_profile DROP COLUMN IF EXISTS mukim'))
    bind.execute(sa.text(f'ALTER TABLE "{p}".sales_profile DROP COLUMN IF EXISTS state'))
    bind.execute(sa.text(f'DROP TABLE IF EXISTS "{p}".project_registrations'))
