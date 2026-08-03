"""Let an attachment belong to a Dealer Kit asset.

`attachments.entity_type` is constrained to an explicit LIST of strings by
`attachments_entity_type_check`, and `dealer_kit_asset` was not on it. So every
flyer banner the reader stores was rejected by the database at INSERT: the bytes
reached R2, the attachment row did not, the reading logged a warning and carried
on, and the seeded catalogue came out with no artwork at all. Silent, because
storing a banner is best-effort by design (see `_store_banners`) - the upload
still returned 201.

**Nothing in the test suite could have caught this**, which is the part worth
remembering. The constraint lives ONLY in a migration (070), never on the model,
and every scratch-schema test builds its tables with `Base.metadata.create_all` -
which emits the columns and knows nothing about a constraint added by an ALTER.
So the whole artwork suite passed on a schema that was missing the one rule the
real database enforces. A new `entity_type` value therefore has to be added HERE,
and adding it to a model or a service is not enough.

The list is restated in full rather than patched, because a CHECK cannot be
extended in place: Postgres has no ADD VALUE for one, so drop and recreate is the
only shape available. Every value from 070 is carried forward unchanged.

**Applied to the shared dev database by hand, NOT stamped.** That database is
stamped at another worktree's revision, so `alembic upgrade` cannot run here and
this DDL was executed against it directly. Both statements are idempotent
(DROP ... IF EXISTS then ADD), so this revision is a no-op where it has already
been applied and still correct on a database that has never seen it.

Revision ID: 317_attachment_dealer_kit_asset
Revises: c0e72e73cb4c
Create Date: 2026-08-02
"""

from alembic import op
from sqlalchemy import text

revision = "317_attachment_dealer_kit_asset"
down_revision = "c0e72e73cb4c"
branch_labels = None
depends_on = None

_WITHOUT_KIT = (
    " 'product', 'promotion', 'complaint', 'general', 'complaint_document',"
    " 'order', 'stock_list', 'form', 'inbound_shipment'"
)
_WITH_KIT = _WITHOUT_KIT + ", 'dealer_kit_asset'"


def _set_allowed(values: str) -> None:
    op.execute(
        text(
            "ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_entity_type_check"
        )
    )
    op.execute(
        text(
            "ALTER TABLE attachments ADD CONSTRAINT attachments_entity_type_check CHECK ("
            f" entity_type IS NULL OR entity_type IN ({values})"
            " )"
        )
    )


def upgrade() -> None:
    _set_allowed(_WITH_KIT)


def downgrade() -> None:
    # Any Kit asset rows would violate the narrower constraint, so they go first.
    # They are library rows for artwork the Kit can re-extract from the flyer.
    #
    # The ASSETS have to go before their attachments: dealer_kit.asset.
    # attachment_id is ON DELETE RESTRICT, so deleting the attachments first
    # raises a foreign key violation - which is exactly the situation this
    # delete exists to avoid, i.e. the downgrade failed whenever there was
    # anything to clean up and worked only when there was not.
    #
    # Guarded on the table existing: a downgrade run from a checkout where the
    # Kit schema was never created should not fail on a missing table.
    op.execute(
        text(
            "DO $$ BEGIN"
            "  IF to_regclass('dealer_kit.asset') IS NOT NULL THEN"
            "    DELETE FROM dealer_kit.asset WHERE attachment_id IN ("
            "      SELECT id FROM attachments WHERE entity_type = 'dealer_kit_asset'"
            "    );"
            "  END IF;"
            "END $$;"
        )
    )
    op.execute(
        text("DELETE FROM attachments WHERE entity_type = 'dealer_kit_asset'")
    )
    _set_allowed(_WITHOUT_KIT)
