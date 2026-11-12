"""After-sales P1: service jobs, technicians, the complaint Site, the resolution flag.

Plan: documentation/plans/after-sales/PLAN-service-jobs-p1-12nov.md. Additive only.

- ``technicians`` and ``service_jobs`` (job -> complaint FK, technician as a column).
- ``complaints.site_*``: the address a technician goes to (all nullable).
- ``complaint_resolutions.requires_service_job`` (default false).
- Seeds, all idempotent: the service_job status graph, the ``service_job`` numbering rule per
  company, and the three permissions, granted to roles that hold
  ``complaint_management.complaints.edit`` (sync_permissions creates slugs but never grants them).

Revision ID: sj_0001_service_jobs
Revises: qdp_0001_duplicate_party
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "sj_0001_service_jobs"
down_revision = "qdp_0001_duplicate_party"
branch_labels = None
depends_on = None

_PERMS = (
    ("complaint_management.service_jobs.view", "View Service Jobs",
     "See service jobs, the dispatch board and the technician list."),
    ("complaint_management.service_jobs.dispatch", "Dispatch Service Jobs",
     "Raise service jobs, confirm dates, assign technicians and move a job through its steps."),
    ("complaint_management.technicians.manage", "Manage Technicians",
     "Create, edit, archive and delete technicians."),
)
_GRANT_SOURCE_SLUG = "complaint_management.complaints.edit"

_SITE_COLUMNS = (
    ("site_address_line1", "TEXT"),
    ("site_address_line2", "TEXT"),
    ("site_postcode", "TEXT"),
    ("site_city", "TEXT"),
    ("site_state", "TEXT"),
    ("site_country", "TEXT"),
    ("site_contact_name", "TEXT"),
    ("site_contact_phone", "TEXT"),
    ("site_latitude", "NUMERIC(10,7)"),
    ("site_longitude", "NUMERIC(10,7)"),
)


def upgrade() -> None:
    bind = op.get_bind()

    for column, ddl in _SITE_COLUMNS:
        op.execute(f"ALTER TABLE complaints ADD COLUMN IF NOT EXISTS {column} {ddl}")
    op.execute(
        "ALTER TABLE complaint_resolutions "
        "ADD COLUMN IF NOT EXISTS requires_service_job BOOLEAN NOT NULL DEFAULT false"
    )

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
            complaint_id       uuid NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
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
    for name, column in (
        ("ix_service_jobs_complaint_id", "complaint_id"),
        ("ix_service_jobs_status_id", "status_id"),
        ("ix_service_jobs_technician_id", "technician_id"),
        ("ix_service_jobs_scheduled_from", "scheduled_from"),
        ("ix_service_jobs_company_id", "company_id"),
    ):
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON service_jobs ({column})")

    # ---- permissions -------------------------------------------------------
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
    op.execute("DELETE FROM document_numbering_rules WHERE doc_type = 'service_job'")
    op.execute("DROP TABLE IF EXISTS service_jobs")
    op.execute("DELETE FROM status_transitions WHERE entity_type = 'service_job'")
    op.execute("DELETE FROM statuses WHERE entity_type = 'service_job'")
    op.execute("DROP TABLE IF EXISTS technicians")
    op.execute("ALTER TABLE complaint_resolutions DROP COLUMN IF EXISTS requires_service_job")
    for column, _ddl in _SITE_COLUMNS:
        op.execute(f"ALTER TABLE complaints DROP COLUMN IF EXISTS {column}")
