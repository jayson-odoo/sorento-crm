"""Shared brand attachments and folders: the four DDL pieces (PLAN-shared-brand-attachments.md S3, S6).

Four independent changes, bundled into one migration because they land in the
same PR and none has a dependency on the others:

1. ``attachment_types.is_shared`` - an upload of a type flagged shared writes
   ``company_id = NULL`` (R11). Default false: every existing type keeps
   today's behaviour until someone checks the box.
2. ``attachment_directories.company_id`` loses its NOT NULL + its migration-306
   DEFAULT. Folders become shareable the same way attachments already are
   (R17); the ORM column was already ``nullable=True`` (``CompanyScopedMixin``
   keeps it permissive for the test schema), so this is a PG-only unlock, not
   a model change to the column itself. ``AttachmentDirectory.__company_shared__``
   is flipped in the same commit (app/models/resources.py) so the auto-stamp
   and the scope filter agree with what this migration allows.
3. ``uq_certificates_company_scheme_number`` is rebuilt on
   ``coalesce(company_id, '00000000-0000-0000-0000-000000000000')`` so two
   NULL-company (shared) certificates with the same identity cannot coexist -
   a plain unique index treats every NULL as distinct, which would let a
   shared certificate be re-filed indefinitely.
4. ``certificates.company_id`` loses the NOT NULL migration 312 gave it -
   ``Certificate.__company_shared__`` (S4, app/models/certificate.py) makes a
   shared certificate a real, deliberate row (R5: the certificate follows its
   filed attachment's company), and Postgres has to allow writing one. The
   ORM column was already permissive for the test schema, same as piece 2.

Written as ``449_shared_brand_attach`` on ``448_merge_s6b_ptag``. PRs #443 and
#445 were merged into their own stacked bases rather than into main, so this
file never reached main while main grew 449 -> 452; it is renumbered and
re-parented onto ``452_transfer_days`` so the graph keeps one head. Nothing in
it depends on 449-452 (they touch dealer-kit, spec and SCM tables only) and
every step is already guarded, so replaying it is a no-op wherever it was
applied by hand.

Revision ID: 453_shared_brand_attach
Revises: 452_transfer_days
"""
from alembic import op
import sqlalchemy as sa

revision = "453_shared_brand_attach"
down_revision = "452_transfer_days"
branch_labels = None
depends_on = None

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_NULL_IDENTITY_SENTINEL = "00000000-0000-0000-0000-000000000000"


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = current_schema()"
            ),
            {"t": table},
        )
    }


def upgrade() -> None:
    # --- 1. attachment_types.is_shared ------------------------------------
    if "is_shared" not in _columns("attachment_types"):
        op.add_column(
            "attachment_types",
            sa.Column(
                "is_shared", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )

    # --- 2. attachment_directories.company_id -> nullable, no default -----
    ad_columns = _columns("attachment_directories")
    if "company_id" in ad_columns:
        op.execute(
            "ALTER TABLE attachment_directories ALTER COLUMN company_id DROP NOT NULL"
        )
        op.execute(
            "ALTER TABLE attachment_directories ALTER COLUMN company_id DROP DEFAULT"
        )

    # --- 3. certificate identity index: NULL-safe on company_id -----------
    cert_columns = _columns("certificates")
    if cert_columns:
        op.execute("DROP INDEX IF EXISTS uq_certificates_company_scheme_number")
        op.execute(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_certificates_company_scheme_number
                ON certificates (
                    coalesce(company_id, '{_NULL_IDENTITY_SENTINEL}'),
                    upper(regexp_replace(scheme || certificate_number, '[^A-Za-z0-9]', '', 'g'))
                )
            """
        )

    # --- 4. certificates.company_id -> nullable (a shared certificate) -----
    if "company_id" in cert_columns:
        op.execute("ALTER TABLE certificates ALTER COLUMN company_id DROP NOT NULL")


def downgrade() -> None:
    # --- 3a. drop the coalesced identity index FIRST ------------------------
    # It must be gone before the piece-4 stamp below: that UPDATE moves a
    # shared (NULL) certificate's company_id to Sorento, and the COALESCED
    # index treats NULL and Sorento as different keys - a certificate already
    # sharing Sorento's identity would make the UPDATE itself collide against
    # a still-live unique index mid-statement. Dropping it first means the
    # UPDATE always succeeds; a genuine duplicate then surfaces cleanly at the
    # plain index's CREATE below, not as a confusing UPDATE failure.
    cert_columns = _columns("certificates")
    if cert_columns:
        op.execute("DROP INDEX IF EXISTS uq_certificates_company_scheme_number")

    # --- 4. certificates.company_id -> NOT NULL again -----------------------
    if "company_id" in cert_columns:
        # A certificate shared while this migration was up has NULL here;
        # stamp it to the incumbent company first, same pattern as piece 2.
        op.execute(
            f"UPDATE certificates SET company_id = '{SORENTO_COMPANY_ID}' "
            f"WHERE company_id IS NULL"
        )
        op.execute("ALTER TABLE certificates ALTER COLUMN company_id SET NOT NULL")

    # --- 3b. restore the plain (non-coalesced) certificate identity index --
    if cert_columns:
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_certificates_company_scheme_number
                ON certificates (
                    company_id,
                    upper(regexp_replace(scheme || certificate_number, '[^A-Za-z0-9]', '', 'g'))
                )
            """
        )

    # --- 2. attachment_directories.company_id -> NOT NULL again -----------
    ad_columns = _columns("attachment_directories")
    if "company_id" in ad_columns:
        # A folder shared while this migration was up has NULL here; stamp it
        # to the incumbent company before the NOT NULL flip, exactly like
        # migration 305 did for every other owned table.
        op.execute(
            f"UPDATE attachment_directories SET company_id = '{SORENTO_COMPANY_ID}' "
            f"WHERE company_id IS NULL"
        )
        op.execute(
            "ALTER TABLE attachment_directories ALTER COLUMN company_id SET NOT NULL"
        )
        op.execute(
            f"ALTER TABLE attachment_directories ALTER COLUMN company_id "
            f"SET DEFAULT '{SORENTO_COMPANY_ID}'"
        )

    # --- 1. drop attachment_types.is_shared --------------------------------
    if "is_shared" in _columns("attachment_types"):
        op.drop_column("attachment_types", "is_shared")
