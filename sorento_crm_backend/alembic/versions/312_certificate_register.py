"""Certificate register: identity + revisions + coverage, and the attachment-type gate.

Certification PDFs stop being anonymous attachments and become a register with expiry,
renewal history and product coverage. Three tables plus two columns on
``attachment_types``.

Three details worth reading before editing this file:

**Identity includes the SCHEME, not just the number.** Live data has certificate number
``04124FC`` under BOTH the ``PPS`` and ``SPAN`` schemes with different expiry dates
(2027-04-01 vs 2029-04-05) - the same IKRAM test-report reference approved under two
regulatory schemes. Keying identity on the number alone would merge those two rows and
silently overwrite the earlier expiry, so the unique index spans the normalized
``scheme || certificate_number`` within a company.

**Validity is never stored.** There is no ``expired`` / ``expiring_soon`` column and the
status CHECK rejects those values. Validity is derived at read time from the current
revision's dates, exactly like ``promotions.is_expired``. A stored expiry state becomes a
lie the first day the scheduler does not run.

**sync_permissions creates slugs but never grants them.** The registry sync at startup
will create the ``master_data.certificates.*`` rows, but a permission granted to nobody is
indistinguishable from a broken feature, so the grants are copied here from the existing
``master_data.product_attachments.*`` holders.

Idempotent raw SQL, safe to re-run.

Revision ID: 311_certificate_register
Revises: 310_form_sla_skip_stage
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "312_certificate_register"
# Re-chained off 311_split_pr_approve_permission (merged to main as PR #71)
# rather than 310: both cannot descend from the same parent or alembic has
# two heads and every upgrade fails with "Multiple heads are present".
down_revision = "311_split_pr_approve_permission"
branch_labels = None
depends_on = None


_PERMS = (
    ("master_data.certificates.view", "View Certificates", "Permission to view Certificates."),
    ("master_data.certificates.add", "Add Certificates", "Permission to add Certificates."),
    ("master_data.certificates.edit", "Edit Certificates", "Permission to edit Certificates."),
    ("master_data.certificates.delete", "Delete Certificates", "Permission to delete Certificates."),
    ("master_data.certificates.export", "Export Certificates", "Permission to export Certificates."),
)

# Grants are copied from the holders of this slug: certificates are a product-master
# concern, so whoever may already see product attachments may see certificates.
_GRANT_SOURCE_SLUG = "master_data.product_attachments.view"


def _has_column(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    # ---- attachment_types: the cert-bearing gate -------------------------------
    # Non-null certificate behaviour is driven off is_certificate rather than the type
    # name, so a future client adds a cert kind by creating an attachment type and
    # ticking a box. max_validity_months backs the plausibility check that flags a
    # hallucinated extraction date.
    if not _has_column(bind, "attachment_types", "is_certificate"):
        op.add_column(
            "attachment_types",
            sa.Column(
                "is_certificate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if not _has_column(bind, "attachment_types", "max_validity_months"):
        op.add_column(
            "attachment_types",
            sa.Column("max_validity_months", sa.Integer(), nullable=True),
        )

    # The column defaults to false, so without this the live "Certification" type
    # would be non-cert-bearing and the ingest guard would drop every extracted
    # certificate silently - the feature would be installed but inert, which is
    # indistinguishable from broken. Seed the one type that exists today; further
    # types are an admin action.
    bind.execute(
        sa.text(
            "UPDATE attachment_types SET is_certificate = true "
            "WHERE type_name = 'Certification' AND is_certificate = false"
        )
    )

    # ---- certificates: the IDENTITY -------------------------------------------
    # company_id is NOT NULL in Postgres while the ORM mixin keeps it nullable - the
    # same split migrations 305/306 apply to the other owned tables. The auto-stamp in
    # company_scope fills it on every ORM insert; the constraint is what makes a raw
    # INSERT that bypasses the stamp fail loudly instead of creating an unscoped row.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS certificates (
            id                                   uuid PRIMARY KEY,
            company_id                           uuid NOT NULL REFERENCES companies(id),
            attachment_type_id                   uuid REFERENCES attachment_types(id) ON DELETE SET NULL,
            scheme                               varchar(60)  NOT NULL,
            certifying_body                      varchar(120),
            certificate_number                   varchar(120) NOT NULL,
            issuer                               varchar(200),
            title                                text,
            status                               varchar(20)  NOT NULL DEFAULT 'active',
            current_revision_id                  uuid,
            possible_duplicate_of_certificate_id uuid REFERENCES certificates(id) ON DELETE SET NULL,
            expiry_notified_at                   timestamp,
            expiry_notify_batch_id               uuid,
            created_at                           timestamp    NOT NULL DEFAULT now(),
            updated_at                           timestamp    NOT NULL DEFAULT now(),
            created_by                           uuid,
            CONSTRAINT ck_certificates_status
                CHECK (status IN ('active', 'archived'))
        )
        """
    )

    # Identity. Normalizing away punctuation and case makes "PPS 0119", "PPS-0119" and
    # "pps0119" the same certificate, while the scheme prefix keeps PPS/04124FC and
    # SPAN/04124FC apart.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_certificates_company_scheme_number
            ON certificates (
                company_id,
                upper(regexp_replace(scheme || certificate_number, '[^A-Za-z0-9]', '', 'g'))
            )
        """
    )
    for column in ("company_id", "attachment_type_id", "status", "scheme"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_certificates_{column} ON certificates ({column})"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_certificates_expiry_notify_batch_id "
        "ON certificates (expiry_notify_batch_id)"
    )
    # Backs the pg_trgm near-match probe that flags an OCR-mangled number as a possible
    # renewal instead of silently forking a second certificate.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_certificates_number_trgm "
        "ON certificates USING gin (certificate_number gin_trgm_ops)"
    )

    # ---- certificate_revisions: one row per issue ------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS certificate_revisions (
            id                 uuid PRIMARY KEY,
            certificate_id     uuid NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
            revision_no        integer NOT NULL,
            attachment_id      uuid REFERENCES attachments(id) ON DELETE SET NULL,
            issued_at          date,
            valid_from         date,
            valid_until        date,
            is_current         boolean NOT NULL DEFAULT false,
            source             varchar(10) NOT NULL DEFAULT 'ai',
            needs_review       boolean NOT NULL DEFAULT false,
            review_reasons     jsonb NOT NULL DEFAULT '[]'::jsonb,
            extracted_json     jsonb,
            unmatched_products jsonb NOT NULL DEFAULT '[]'::jsonb,
            reviewed_at        timestamp,
            reviewed_by        uuid,
            created_at         timestamp NOT NULL DEFAULT now(),
            created_by         uuid,
            CONSTRAINT ck_certificate_revisions_source
                CHECK (source IN ('ai', 'manual'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_certificate_revisions_cert_no
            ON certificate_revisions (certificate_id, revision_no)
        """
    )
    # At most ONE current revision per certificate. Partial, so superseded rows are
    # unconstrained.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_certificate_revisions_one_current
            ON certificate_revisions (certificate_id)
            WHERE is_current
        """
    )
    for column in ("certificate_id", "attachment_id", "valid_until", "needs_review"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_certificate_revisions_{column} "
            f"ON certificate_revisions ({column})"
        )

    # certificates.current_revision_id is deliberately added as an FK only AFTER the
    # revisions table exists, otherwise the CREATE TABLE above would forward-reference.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_certificates_current_revision'
            ) THEN
                ALTER TABLE certificates
                    ADD CONSTRAINT fk_certificates_current_revision
                    FOREIGN KEY (current_revision_id)
                    REFERENCES certificate_revisions(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )

    # ---- certificate_products: coverage, the source of truth -------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS certificate_products (
            id             uuid PRIMARY KEY,
            certificate_id uuid NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
            product_id     uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            source         varchar(10) NOT NULL DEFAULT 'ai',
            created_at     timestamp NOT NULL DEFAULT now(),
            created_by     uuid,
            CONSTRAINT ck_certificate_products_source
                CHECK (source IN ('ai', 'manual'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_certificate_products_unique
            ON certificate_products (certificate_id, product_id)
        """
    )
    for column in ("certificate_id", "product_id"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_certificate_products_{column} "
            f"ON certificate_products ({column})"
        )

    # Re-run safety: an earlier apply of this revision created the table without the
    # NOT NULL above, so bring an existing table up to spec. No-op on a fresh create.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'certificates'
                   AND column_name = 'company_id'
                   AND is_nullable = 'YES'
            ) AND NOT EXISTS (SELECT 1 FROM certificates WHERE company_id IS NULL) THEN
                ALTER TABLE certificates ALTER COLUMN company_id SET NOT NULL;
            END IF;
        END $$
        """
    )

    # ---- permissions ------------------------------------------------------------
    # The registry sync at startup creates these, but a fresh deploy runs migrations
    # first - insert here so the grants below always have a target.
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

    # Copy grants from the product-attachments view holders. sync_permissions never
    # grants, so without this every existing role would see the feature as missing.
    for slug, _name, _descr in _PERMS:
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


def downgrade() -> None:
    bind = op.get_bind()

    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text(
                """
                DELETE FROM user_role_permissions
                 WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug},
        )
    for slug, _name, _descr in _PERMS:
        bind.execute(
            sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": slug}
        )

    op.execute("ALTER TABLE IF EXISTS certificates DROP CONSTRAINT IF EXISTS fk_certificates_current_revision")
    op.execute("DROP TABLE IF EXISTS certificate_products")
    op.execute("DROP TABLE IF EXISTS certificate_revisions")
    op.execute("DROP TABLE IF EXISTS certificates")

    for name in ("max_validity_months", "is_certificate"):
        if _has_column(bind, "attachment_types", name):
            op.drop_column("attachment_types", name)
