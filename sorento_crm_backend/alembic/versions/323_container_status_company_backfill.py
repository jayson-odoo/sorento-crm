"""Attribute every Container Status workbook to a company.

`attachments` is the one owned table that stays nullable, because NULL means
"shared form attachment". For a Container Status workbook that reading is wrong:
the sheet is an OWNED operational document, and `Attachment.__company_shared__`
makes a NULL row visible to every company at once. Worse, `enforce_single_current`
ranks NULLs only against other NULLs, so a NULL workbook can never be superseded
by any company's future import - a single-company caller resolves TWO current
workbooks, one labelled with their company and one labelled nothing, which is the
exact ambiguity the per-company rule exists to remove.

Two ways such a row exists today:

* `JobService.active_company_id_from_scope` snapshots a NULL `company_id` on an
  import enqueued without a single-company scope (the n8n / X-API-Key path), and
  publication copied that snapshot straight onto the attachment.
* Migration 302's attachment backfill stamped only positively-owned attachments
  (a directory, or a product / promotion / shipment link). A published container
  status workbook has none of those, so it was skipped.

The publication path is fixed at source (`publish_import_source` now coalesces the
job snapshot onto the incumbent company). This migration cleans up the rows that
already landed: Sorento is the incumbent company, every pre-isolation row was
backfilled to it (302/305) and migration 306 made it the DB DEFAULT for owned
tables, so an unattributed owned row belongs to Sorento.

JOIN-based against `attachment_types` so it selects rows by what they ARE rather
than by a hardcoded id list, and idempotent: a second run finds nothing left to
stamp. A row already attributed to another company is left alone - the mismatch
being corrected here is "unattributed", not "attributed to the wrong company",
and re-pointing a real Mocha workbook at Sorento would be the destructive answer.

`is_deleted` is deliberately untouched. Rows the old global rule already trashed
stay trashed - this only attributes them, it does not resurrect anything.

Revision ID: 323_cs_company_backfill
Revises: 322_merge_dealer_kit_customers
"""
from alembic import op


# Kept <= 32 chars: alembic_version.version_num is varchar(32) on the stamp path.
revision = "323_cs_company_backfill"
down_revision = "322_merge_dealer_kit_customers"
branch_labels = None
depends_on = None

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE attachments a
        SET company_id = '{SORENTO_COMPANY_ID}'
        FROM attachment_types t
        WHERE t.id = a.attachment_type_id
          AND (t.code = 'container_status' OR t.type_name = 'Container Status')
          AND a.company_id IS NULL
        """
    )


def downgrade() -> None:
    """Deliberate no-op.

    Reversing this would mean setting `company_id` back to NULL on Container
    Status attachments, and there is no way to tell the rows this migration
    stamped from the ones a Sorento-scoped import stamped legitimately. Nulling
    both would re-create the every-company-sees-it defect on real data to undo a
    pure attribution fix, so the honest reverse of "attribute the unattributed" is
    to leave the attribution in place.
    """
