"""After-sales P2: the warranty engine tables and the product lines on a service job.

Plan: documentation/plans/after-sales/PLAN-warranty-p2-12nov.md. Additive only; no complaint table is
touched.

- `warranty_product_kinds`, `warranty_kind_rules` (shared by every company), `warranty_policies`
  (company scoped) and `warranty_terms` (reached through its policy).
- `service_job_products`: a job's product lines (kind, purchase date, defect). Cascades with the job.
- The v15 policy seed (kinds, defect set, rules) and each company's v15 policy, idempotent.

Revision ID: wp2_0001_warranty
Revises: ocn_0001_order_change_notice
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "wp2_0001_warranty"
down_revision = "ocn_0001_order_change_notice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS warranty_product_kinds (
            id          uuid PRIMARY KEY,
            code        varchar(64) NOT NULL UNIQUE,
            name        varchar(255) NOT NULL,
            sort_order  integer NOT NULL DEFAULT 0,
            is_active   boolean NOT NULL DEFAULT true,
            created_at  timestamp NOT NULL DEFAULT now(),
            updated_at  timestamp
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_product_kinds_is_active ON warranty_product_kinds (is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_product_kinds_sort_order ON warranty_product_kinds (sort_order)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS warranty_kind_rules (
            id          uuid PRIMARY KEY,
            kind_id     uuid NOT NULL REFERENCES warranty_product_kinds(id) ON DELETE CASCADE,
            match_type  varchar(20) NOT NULL,
            match_value text NOT NULL,
            priority    integer NOT NULL DEFAULT 0,
            created_at  timestamp NOT NULL DEFAULT now(),
            updated_at  timestamp
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_kind_rules_kind_id ON warranty_kind_rules (kind_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_kind_rules_match_type ON warranty_kind_rules (match_type)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS warranty_policies (
            id                   uuid PRIMARY KEY,
            version              varchar(32) NOT NULL,
            effective_from       date NOT NULL,
            effective_to         date,
            source_attachment_id uuid REFERENCES attachments(id) ON DELETE SET NULL,
            policy_text          text,
            company_id           uuid NOT NULL REFERENCES companies(id),
            created_at           timestamp NOT NULL DEFAULT now(),
            updated_at           timestamp,
            CONSTRAINT uq_warranty_policies_company_version UNIQUE (company_id, version)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_policies_effective_from ON warranty_policies (effective_from)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_policies_effective_to ON warranty_policies (effective_to)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_policies_company_id ON warranty_policies (company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS warranty_terms (
            id                      uuid PRIMARY KEY,
            policy_id               uuid NOT NULL REFERENCES warranty_policies(id) ON DELETE CASCADE,
            kind_id                 uuid NOT NULL REFERENCES warranty_product_kinds(id) ON DELETE CASCADE,
            part_name               varchar(120) NOT NULL,
            duration_months         integer,
            is_lifetime             boolean NOT NULL DEFAULT false,
            covered_defect_type_ids uuid[],
            installation_included   boolean NOT NULL DEFAULT false,
            qualifications          text,
            exclusions              text,
            created_at              timestamp NOT NULL DEFAULT now(),
            updated_at              timestamp,
            CONSTRAINT uq_warranty_terms_policy_kind_part UNIQUE (policy_id, kind_id, part_name),
            CONSTRAINT ck_warranty_terms_duration_xor_lifetime CHECK (
                (is_lifetime AND duration_months IS NULL) OR
                (NOT is_lifetime AND duration_months IS NOT NULL AND duration_months > 0)
            )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_warranty_terms_policy_kind ON warranty_terms (policy_id, kind_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_job_products (
            id             uuid PRIMARY KEY,
            service_job_id uuid NOT NULL REFERENCES service_jobs(id) ON DELETE CASCADE,
            product_id     uuid NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            kind_id        uuid REFERENCES warranty_product_kinds(id) ON DELETE RESTRICT,
            purchase_date  date,
            defect_type_id uuid REFERENCES lookup_options(id) ON DELETE SET NULL,
            sort_order     integer NOT NULL DEFAULT 0,
            company_id     uuid NOT NULL REFERENCES companies(id),
            created_at     timestamp NOT NULL DEFAULT now(),
            updated_at     timestamp
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_service_job_products_job ON service_job_products (service_job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_service_job_products_kind_id ON service_job_products (kind_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_service_job_products_company_id ON service_job_products (company_id)")

    # ---- v15 seed: shared kinds / defect set / rules, and one policy per company ----
    from app.services.warranty_seed import seed_warranty_policy_v15

    session = Session(bind=bind)
    try:
        for (company_id,) in session.execute(sa.text("SELECT id FROM companies")).all():
            seed_warranty_policy_v15(session, str(company_id))
        session.flush()
    finally:
        session.close()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_job_products")
    op.execute("DROP TABLE IF EXISTS warranty_terms")
    op.execute("DROP TABLE IF EXISTS warranty_policies")
    op.execute("DROP TABLE IF EXISTS warranty_kind_rules")
    op.execute("DROP TABLE IF EXISTS warranty_product_kinds")
