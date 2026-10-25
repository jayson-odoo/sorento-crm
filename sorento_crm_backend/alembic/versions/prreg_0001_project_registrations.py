"""PROJECT-REG-PORTAL: portal project registrations as projects, the profile's state, mukim
and legacy fields, the two lookup sets the form reads, the approve permission and the PPF
project numbering rule.

Idempotent (`IF NOT EXISTS`, `WHERE NOT EXISTS`, `ON CONFLICT`) so the shared dev DB, which
converges through `create_all`, can take it in any order.

- A portal registration IS a `projects.projects` row (owner ruling 25 Oct 17:50, PLAN R1, R12):
  `project_code` becomes nullable (no code until Approve), and the row gains `approval_state`
  (NULL for staff projects), `reject_reason`, `submitted_at`, `decided_at`, `decided_by`.
  There is no registrations table: this revision neither creates nor drops
  `projects.project_registrations` (the first version of it created one; dropping that on a
  database that ran it is held for the owner).
- The identity index `uq_projects_company_developer_title` becomes PARTIAL over staff and
  approved rows (R3), so a pending, rejected or draft registration neither collides nor
  blocks. A full index from before the rework is replaced, not kept.
- `projects.sales_profile` gains `state` / `mukim` (D12) and the portal-only legacy fields.
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


INDEX = "uq_projects_company_developer_title"
#: R3: only staff projects (NULL) and approved registrations hold the registration lock.
INDEX_WHERE = "approval_state IS NULL OR approval_state = 'approved'"

#: `projects.projects` columns (R1), in add order.
PROJECT_COLUMNS = (
    ("approval_state", "VARCHAR(16)"),
    ("reject_reason", "TEXT"),
    ("submitted_at", "TIMESTAMP"),
    ("decided_at", "TIMESTAMP"),
    ("decided_by", "VARCHAR(100) REFERENCES public.users(id) ON DELETE SET NULL"),
)
#: `projects.sales_profile` columns: state and mukim (D12) and the portal-only legacy fields.
PROFILE_COLUMNS = (
    ("state", "VARCHAR(100)"),
    ("mukim", "VARCHAR(255)"),
    ("contact_id", "TEXT REFERENCES public.respond_contacts(id) ON DELETE SET NULL"),
    ("sales_agent_id", "UUID REFERENCES public.sales_agents(id) ON DELETE SET NULL"),
    ("distributor_name", "VARCHAR(255)"),
    ("customer_id", "UUID REFERENCES public.customers(id) ON DELETE SET NULL"),
    ("customer_name", "VARCHAR(255)"),
    ("your_ref", "VARCHAR(255)"),
    ("type_of_building", "VARCHAR(255)"),
    ("developer_name", "VARCHAR(255)"),
    ("main_contractor_name", "VARCHAR(255)"),
    ("architect_name", "VARCHAR(255)"),
)


def _index_def(bind, p: str):
    return bind.execute(
        sa.text("SELECT indexdef FROM pg_indexes WHERE schemaname = :s AND indexname = :n"),
        {"s": p, "n": INDEX},
    ).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    p = _schema(bind, "projects")
    statements = [
        f'CREATE SCHEMA IF NOT EXISTS "{p}"',
        f'ALTER TABLE "{p}".projects ALTER COLUMN project_code DROP NOT NULL',
    ]
    statements += [
        f'ALTER TABLE "{p}".projects ADD COLUMN IF NOT EXISTS {name} {ddl}' for name, ddl in PROJECT_COLUMNS
    ]
    statements += [
        f'ALTER TABLE "{p}".sales_profile ADD COLUMN IF NOT EXISTS {name} {ddl}' for name, ddl in PROFILE_COLUMNS
    ]
    statements.append(
        f'CREATE INDEX IF NOT EXISTS ix_project_sales_profile_contact ON "{p}".sales_profile (contact_id)'
    )
    for statement in statements:
        bind.execute(sa.text(statement))

    # The identity index becomes partial. A FULL one (from before the rework, or built from
    # the old model) carries the same name, so `IF NOT EXISTS` alone would keep it.
    current = _index_def(bind, p)
    if current and "WHERE" not in current.upper():
        bind.execute(sa.text(f'DROP INDEX "{p}".{INDEX}'))
    bind.execute(
        sa.text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON "{p}".projects '
            f"(company_id, developer_party_id, normalised_title) NULLS NOT DISTINCT "
            f"WHERE ({INDEX_WHERE})"
        )
    )

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

    # Documented data loss: a portal registration that was never approved has no code, and
    # the code column goes back to NOT NULL, so draft / pending / rejected rows go (their
    # sales profiles cascade). Approved and staff projects all carry a code and stay.
    bind.execute(sa.text(f'DELETE FROM "{p}".projects WHERE project_code IS NULL'))
    bind.execute(sa.text(f'DROP INDEX IF EXISTS "{p}".{INDEX}'))
    bind.execute(
        sa.text(
            f'CREATE UNIQUE INDEX {INDEX} ON "{p}".projects '
            "(company_id, developer_party_id, normalised_title) NULLS NOT DISTINCT"
        )
    )
    bind.execute(sa.text(f'ALTER TABLE "{p}".projects ALTER COLUMN project_code SET NOT NULL'))
    bind.execute(sa.text(f'DROP INDEX IF EXISTS "{p}".ix_project_sales_profile_contact'))
    for name, _ddl in reversed(PROFILE_COLUMNS):
        bind.execute(sa.text(f'ALTER TABLE "{p}".sales_profile DROP COLUMN IF EXISTS {name}'))
    for name, _ddl in reversed(PROJECT_COLUMNS):
        bind.execute(sa.text(f'ALTER TABLE "{p}".projects DROP COLUMN IF EXISTS {name}'))
