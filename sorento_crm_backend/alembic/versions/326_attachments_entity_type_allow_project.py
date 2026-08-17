"""Allow `project` (and `project_lead`) as an attachment entity_type.

Found in the browser while wiring the project Documents tab: the upload stored its bytes in R2
and then died on `attachments_entity_type_check`, because that CHECK carries a hardcoded list of
entity types and nobody added the ones this module uses. The endpoint itself is generic - it
takes any `entity_type` on the form and writes the `entity_attachment_links` row - so the
constraint was the only thing refusing.

`project_lead` goes in at the same time: a tender notice attached to the lead it arrived on is
the same want, one screen earlier, and discovering this a second time is waste.

Rebuilt rather than extended in place, because Postgres has no "add a value to a CHECK": the old
constraint is dropped and the full list re-declared. Every previously allowed value is carried
over verbatim.

Revision ID: 326_attachments_entity_type_allow_project
Revises: 325_registered_is_the_first_rung
"""
from alembic import op
from sqlalchemy import text


revision = "326_attachments_entity_type_allow_project"
down_revision = "325_registered_is_the_first_rung"
branch_labels = None
depends_on = None

_BEFORE = (
    "product",
    "promotion",
    "complaint",
    "general",
    "complaint_document",
    "order",
    "stock_list",
    "form",
    "inbound_shipment",
    "dealer_kit_asset",
)
_ADDED = ("project", "project_lead")


def _apply(values: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        text("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_entity_type_check")
    )
    op.execute(
        text(
            "ALTER TABLE attachments ADD CONSTRAINT attachments_entity_type_check CHECK ("
            f"entity_type IS NULL OR entity_type IN ({listed}))"
        )
    )


def upgrade() -> None:
    _apply(_BEFORE + _ADDED)


def downgrade() -> None:
    # Rows written meanwhile would violate the narrower constraint, so clear them first rather
    # than leaving the downgrade to fail halfway.
    op.execute(
        text(
            "update attachments set entity_type = 'general' "
            "where entity_type in ('project', 'project_lead')"
        )
    )
    _apply(_BEFORE)
