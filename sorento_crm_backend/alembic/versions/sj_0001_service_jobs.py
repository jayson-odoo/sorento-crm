"""After-sales P1: service jobs and technicians, the standalone After-sales module.

Plan: documentation/plans/after-sales/PLAN-service-jobs-p1-12nov.md. Additive only, and it changes
nothing in the live Complaints module (owner ruling, 12 Nov 2026): no column on `complaints` or
`complaint_resolutions`.

- `technicians` and `service_jobs`. A job carries its own customer, contact, site and problem;
  `complaint_id` is an OPTIONAL reference (FK on the job side only, SET NULL).
- The `after_sales` module: a catalog row, enabled for every tenant that already has module rows
  (so a strict module guard does not hide the screens).
- Seeds, all idempotent: the service_job status graph, the `service_job` numbering rule per company,
  and the three `after_sales.*` permissions, granted to roles that hold
  `complaint_management.complaints.edit` (sync_permissions creates slugs but never grants them).
  Rows holding the earlier `complaint_management.*` spelling of the same three slugs are renamed.

Revision ID: sj_0001_service_jobs
Revises: prr_0001_si_npa_project
Create Date: 2026-11-12
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "sj_0001_service_jobs"
down_revision = "prr_0001_si_npa_project"
branch_labels = None
depends_on = None

_PERMS = (
    ("after_sales.service_jobs.view", "View Service Jobs",
     "See service jobs, the dispatch board and the technician list."),
    ("after_sales.service_jobs.dispatch", "Dispatch Service Jobs",
     "Create service jobs, confirm dates, assign technicians and move a job through its steps."),
    ("after_sales.technicians.manage", "Manage Technicians",
     "Create, edit, archive and delete technicians."),
)
_OLD_SLUGS = {
    "complaint_management.service_jobs.view": "after_sales.service_jobs.view",
    "complaint_management.service_jobs.dispatch": "after_sales.service_jobs.dispatch",
    "complaint_management.technicians.manage": "after_sales.technicians.manage",
}
_GRANT_SOURCE_SLUG = "complaint_management.complaints.edit"

_JOB_TEXT_COLUMNS = (
    "customer_name",
    "contact_name",
    "contact_phone",
    "site_address_line1",
    "site_address_line2",
    "site_postcode",
    "site_city",
    "site_state",
    "site_country",
    "problem",
)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS technicians (
            id              uuid PRIMARY KEY,
            name            varchar(255) NOT NULL,
            phone           varchar(32),
            employment_type varchar(20),
            is_active       boolean NOT NULL DEFAULT true,
            company_id      uuid NOT NULL REFERENCES companies(id),
            created_at      timestamp NOT NULL DEFAULT now(),
            updated_at      timestamp
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_technicians_name ON technicians (name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_technicians_company_id ON technicians (company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_jobs (
            id                 uuid PRIMARY KEY,
            job_number         varchar(64) UNIQUE,
            complaint_id       uuid REFERENCES complaints(id) ON DELETE SET NULL,
            customer_name      text NOT NULL DEFAULT '',
            contact_name       text,
            contact_phone      text,
            site_address_line1 text,
            site_address_line2 text,
            site_postcode      text,
            site_city          text,
            site_state         text,
            site_country       text,
            problem            text,
            status_id          uuid REFERENCES statuses(id) ON DELETE SET NULL,
            technician_id      uuid REFERENCES technicians(id) ON DELETE SET NULL,
            scheduled_from     timestamp,
            scheduled_to       timestamp,
            customer_agreed_by text,
            rejection_reason   text,
            cancel_reason      text,
            arrived_at         timestamp,
            completed_at       timestamp,
            verified_at        timestamp,
            created_by         varchar,
            company_id         uuid NOT NULL REFERENCES companies(id),
            created_at         timestamp NOT NULL DEFAULT now(),
            updated_at         timestamp
        )
        """
    )
    # A copy that ran an earlier spelling of this revision gets the new shape too.
    op.execute("ALTER TABLE service_jobs ALTER COLUMN complaint_id DROP NOT NULL")
    for column in _JOB_TEXT_COLUMNS:
        default = " NOT NULL DEFAULT ''" if column == "customer_name" else ""
        op.execute(f"ALTER TABLE service_jobs ADD COLUMN IF NOT EXISTS {column} text{default}")
    for name, column in (
        ("ix_service_jobs_complaint_id", "complaint_id"),
        ("ix_service_jobs_customer_name", "customer_name"),
        ("ix_service_jobs_status_id", "status_id"),
        ("ix_service_jobs_technician_id", "technician_id"),
        ("ix_service_jobs_scheduled_from", "scheduled_from"),
        ("ix_service_jobs_company_id", "company_id"),
    ):
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON service_jobs ({column})")

    # ---- permissions -------------------------------------------------------
    for old, new in _OLD_SLUGS.items():
        bind.execute(
            sa.text(
                "UPDATE user_permissions SET slug = :new WHERE slug = :old "
                "AND NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :new)"
            ),
            {"old": old, "new": new},
        )
    for slug, name, descr in _PERMS:
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
                SELECT gen_random_uuid()::text, urp.role_id, tgt.id, now()
                  FROM user_role_permissions urp
                  JOIN user_permissions src ON src.id = urp.permission_id
                 CROSS JOIN user_permissions tgt
                 WHERE src.slug = :source_slug
                   AND tgt.slug = :slug
                ON CONFLICT DO NOTHING
                """
            ),
            {"source_slug": _GRANT_SOURCE_SLUG, "slug": slug},
        )

    # ---- the module --------------------------------------------------------
    bind.execute(
        sa.text(
            """
            INSERT INTO app_modules_catalog
                (id, module_key, display_name, description, sort_order, is_core, dependencies)
            VALUES (:id, 'after_sales', 'After-sales service', :desc, :sort, false, CAST(:deps AS jsonb))
            ON CONFLICT (module_key) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "desc": "Service jobs, the dispatch board and technicians.",
            "sort": "970",
            "deps": '["base", "complaints"]',
        },
    )
    # Enabled wherever the tenant already has module rows; an install with none stays unrestricted.
    bind.execute(
        sa.text(
            """
            INSERT INTO tenant_modules (id, tenant_id, module_key, enabled)
            SELECT gen_random_uuid(), t.tenant_id, 'after_sales', true
              FROM (SELECT DISTINCT tenant_id FROM tenant_modules) t
            ON CONFLICT (tenant_id, module_key) DO NOTHING
            """
        )
    )

    # ---- graph + numbering rule (same functions the app and bootstrap_env use) --
    from app.services import numbering_defaults
    from app.services.service_job_status_graph import seed_service_job_status_graph

    session = Session(bind=bind)
    try:
        seed_service_job_status_graph(session)
        session.flush()
    finally:
        session.close()
    numbering_defaults.seed_service_job_rule(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text(
                "DELETE FROM user_role_permissions WHERE permission_id IN "
                "(SELECT id FROM user_permissions WHERE slug = :slug)"
            ),
            {"slug": slug},
        )
        bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug})
    bind.execute(sa.text("DELETE FROM tenant_modules WHERE module_key = 'after_sales'"))
    bind.execute(sa.text("DELETE FROM app_modules_catalog WHERE module_key = 'after_sales'"))
    op.execute("DELETE FROM document_numbering_rules WHERE doc_type = 'service_job'")
    op.execute("DROP TABLE IF EXISTS service_jobs")
    op.execute("DROP TABLE IF EXISTS technicians")
    op.execute("DELETE FROM status_transitions WHERE entity_type = 'service_job'")
    op.execute("DELETE FROM statuses WHERE entity_type = 'service_job'")
