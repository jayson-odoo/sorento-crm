"""Requestor contact FK + uploader attribution + requestor-selectable segments.

Covers three workstreams in ONE revision so two parallel builds cannot fork the
alembic head:

1. Uploader attribution (PLAN-response-attachments-and-portal-nav, S1):
   `attachments.uploaded_by_contact_id` + `attachments.uploader_kind`. Portal
   uploads previously landed with `uploaded_by = NULL` and no record of WHICH
   contact, so "by contact" vs "by user" was not derivable.

2. Requestor routing (PLAN-requested-by-contact-routing, S1):
   `purchase_requests.requested_by_contact_id` (PR + SF share that table) and
   `stock_inquiries.salesperson_contact_id`. The free-text columns stay as the
   display label / legacy fallback.

3. `market_segments.is_requestor_selectable` - the admin-visible indicator for
   which segments feed the requestor dropdown.

Plus a `response_attachment` attachment type so staff reply files have their own
per-record quota and never consume the contact's `portal_submission` budget.

Every step is idempotent: re-running is a no-op, and a partially-applied state
(from a legacy create_all database) converges instead of failing.

Revision ID: 308_requestor_and_uploader_attribution
Revises: 307_admin_listing_company
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "308_requestor_and_uploader_attribution"
down_revision = "307_admin_listing_company"
branch_labels = None
depends_on = None


# `respond_contacts.id` is TEXT in the live schema (model/column drift predating
# the uuid-id principle), and every existing contact reference follows it
# `purchase_requests.contact_id` and `stock_inquiries.contact_id` are both TEXT.
# The new contact FKs therefore use Text: a UUID column cannot FK to a TEXT key
# ("incompatible types: uuid and text") and would fail at ALTER TABLE time.
CONTACT_FK_TYPE = sa.Text()

RESPONSE_ATTACHMENT_CODE = "response_attachment"
RESPONSE_ATTACHMENT_NAME = "Response Attachment"
# Mirrors portal_submission's whitelist: staff reply with the same media a
# contact would send (phone photos, PDFs, spreadsheets, short videos).
RESPONSE_ATTACHMENT_EXTENSIONS = (
    "3gp,avi,csv,flv,heic,jpeg,jpg,m4v,mkv,mov,mp4,mpeg,mpg,ogv,pdf,png,webm,webp,wmv,xls,xlsx"
)


def _has_table(bind, table: str) -> bool:
    return inspect(bind).has_table(table)


def _columns(bind, table: str) -> set[str]:
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    return {i["name"] for i in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------------- attachments
    if _has_table(bind, "attachments"):
        cols = _columns(bind, "attachments")
        if "uploaded_by_contact_id" not in cols:
            op.add_column(
                "attachments",
                sa.Column("uploaded_by_contact_id", CONTACT_FK_TYPE, nullable=True),
            )
        if "uploader_kind" not in cols:
            op.add_column(
                "attachments",
                sa.Column("uploader_kind", sa.String(length=16), nullable=True),
            )
        if "ix_attachments_uploaded_by_contact_id" not in _indexes(bind, "attachments"):
            op.create_index(
                "ix_attachments_uploaded_by_contact_id",
                "attachments",
                ["uploaded_by_contact_id"],
            )
        # FK only when the target exists (blank scratch schemas build tables in
        # arbitrary order); ON DELETE SET NULL keeps attribution loss non-fatal.
        if _has_table(bind, "respond_contacts"):
            existing_fks = {
                fk.get("name") for fk in inspect(bind).get_foreign_keys("attachments")
            }
            if "fk_attachments_uploaded_by_contact_id" not in existing_fks:
                op.create_foreign_key(
                    "fk_attachments_uploaded_by_contact_id",
                    "attachments",
                    "respond_contacts",
                    ["uploaded_by_contact_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    # ------------------------------------------------------- requestor contact FKs
    for table, column, index_name, fk_name in (
        (
            "purchase_requests",
            "requested_by_contact_id",
            "ix_purchase_requests_requested_by_contact_id",
            "fk_purchase_requests_requested_by_contact_id",
        ),
        (
            "stock_inquiries",
            "salesperson_contact_id",
            "ix_stock_inquiries_salesperson_contact_id",
            "fk_stock_inquiries_salesperson_contact_id",
        ),
    ):
        if not _has_table(bind, table):
            continue
        if column not in _columns(bind, table):
            op.add_column(table, sa.Column(column, CONTACT_FK_TYPE, nullable=True))
        if index_name not in _indexes(bind, table):
            op.create_index(index_name, table, [column])
        if _has_table(bind, "respond_contacts"):
            existing_fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys(table)}
            if fk_name not in existing_fks:
                op.create_foreign_key(
                    fk_name,
                    table,
                    "respond_contacts",
                    [column],
                    ["id"],
                    ondelete="SET NULL",
                )

    # --------------------------------------------------- market segment indicator
    if _has_table(bind, "market_segments"):
        if "is_requestor_selectable" not in _columns(bind, "market_segments"):
            op.add_column(
                "market_segments",
                sa.Column(
                    "is_requestor_selectable",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )

    # ------------------------------------------- response_attachment type (seed)
    if _has_table(bind, "attachment_types"):
        type_cols = _columns(bind, "attachment_types")
        # `code` is nullable in some legacy installs; match on it when present and
        # fall back to type_name so the seed stays single-row either way.
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM attachment_types WHERE code = :code OR type_name = :name LIMIT 1"
            ),
            {"code": RESPONSE_ATTACHMENT_CODE, "name": RESPONSE_ATTACHMENT_NAME},
        ).first()
        if not exists:
            columns = ["code", "type_name", "description", "allowed_extensions", "max_file_size_mb"]
            values = {
                "code": RESPONSE_ATTACHMENT_CODE,
                "type_name": RESPONSE_ATTACHMENT_NAME,
                "description": (
                    "Files attached by staff to a form response (purchasing response, "
                    "technical team response). Separate from portal_submission so staff "
                    "and contact uploads never consume each other's per-record quota."
                ),
                "allowed_extensions": RESPONSE_ATTACHMENT_EXTENSIONS,
                "max_file_size_mb": 100,
            }
            if "max_count_per_entity" in type_cols:
                columns.append("max_count_per_entity")
                values["max_count_per_entity"] = 10
            placeholders = ", ".join(f":{c}" for c in columns)
            # `id` is passed explicitly (gen_random_uuid()): the model declares
            # only a Python-side default, so a create_all-built schema (blank
            # pytest scratch schema, fresh local) has no server default and the
            # insert would fail NOT NULL. Matches every prior seed migration.
            bind.execute(
                sa.text(
                    f"INSERT INTO attachment_types (id, {', '.join(columns)}) "
                    f"VALUES (gen_random_uuid(), {placeholders})"
                ),
                values,
            )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "attachment_types"):
        bind.execute(
            sa.text("DELETE FROM attachment_types WHERE code = :code"),
            {"code": RESPONSE_ATTACHMENT_CODE},
        )

    if _has_table(bind, "market_segments") and "is_requestor_selectable" in _columns(
        bind, "market_segments"
    ):
        op.drop_column("market_segments", "is_requestor_selectable")

    for table, column, index_name, fk_name in (
        (
            "stock_inquiries",
            "salesperson_contact_id",
            "ix_stock_inquiries_salesperson_contact_id",
            "fk_stock_inquiries_salesperson_contact_id",
        ),
        (
            "purchase_requests",
            "requested_by_contact_id",
            "ix_purchase_requests_requested_by_contact_id",
            "fk_purchase_requests_requested_by_contact_id",
        ),
    ):
        if not _has_table(bind, table):
            continue
        existing_fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys(table)}
        if fk_name in existing_fks:
            op.drop_constraint(fk_name, table, type_="foreignkey")
        if index_name in _indexes(bind, table):
            op.drop_index(index_name, table_name=table)
        if column in _columns(bind, table):
            op.drop_column(table, column)

    if _has_table(bind, "attachments"):
        existing_fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys("attachments")}
        if "fk_attachments_uploaded_by_contact_id" in existing_fks:
            op.drop_constraint(
                "fk_attachments_uploaded_by_contact_id", "attachments", type_="foreignkey"
            )
        if "ix_attachments_uploaded_by_contact_id" in _indexes(bind, "attachments"):
            op.drop_index("ix_attachments_uploaded_by_contact_id", table_name="attachments")
        cols = _columns(bind, "attachments")
        if "uploader_kind" in cols:
            op.drop_column("attachments", "uploader_kind")
        if "uploaded_by_contact_id" in cols:
            op.drop_column("attachments", "uploaded_by_contact_id")
