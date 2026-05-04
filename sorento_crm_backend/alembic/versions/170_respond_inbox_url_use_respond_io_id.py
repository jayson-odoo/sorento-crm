"""Backfill respond_inbox_url to use respond_io_id instead of internal RespondContact.id.

Earlier _build_respond_inbox_url paths in procurement_service and complaints_service
embedded the internal RespondContact.id (UUID) as the URL's last path segment. The
Respond.io app + API expect the numeric respond_io_id, so chat opens empty and
``POST /v2/contact/id:<uuid>/message`` returns 400.

This migration rewrites the last segment of respond_inbox_url where it currently
matches a RespondContact.id, replacing it with that contact's respond_io_id, on:

- complaints
- stock_inquiries
- purchase_requests   (covers purchase_request and sponsorship_form rows)

Idempotent JOIN-based update: only rows whose current last segment equals the
RespondContact UUID *and* whose contact has a non-empty respond_io_id are touched.
Rows already pointing at respond_io_id (or unlinked rows) are left alone.

Revision ID: 170_respond_inbox_url_use_respond_io_id
Revises: 169_trigram_indexes_list_search
Create Date: 2026-05-05
"""

from alembic import op


revision = "170_respond_inbox_url_use_respond_io_id"
down_revision = "169_trigram_indexes_list_search"
branch_labels = None
depends_on = None


# Tables that store a respond_inbox_url + a contact_id linking to respond_contacts.id.
TARGET_TABLES = ("complaints", "stock_inquiries", "purchase_requests")


def upgrade() -> None:
    for table in TARGET_TABLES:
        # split_part(..., '/', -1)-style trick: substring after the LAST '/' is the
        # current contact identifier embedded in the URL. We rewrite only when that
        # segment matches the linked RespondContact.id (i.e. it's the broken UUID
        # form), and the contact has a respond_io_id we can substitute in.
        op.execute(
            f"""
            UPDATE {table} AS t
               SET respond_inbox_url = regexp_replace(t.respond_inbox_url, '[^/]+$', rc.respond_io_id)
              FROM respond_contacts rc
             WHERE t.contact_id IS NOT NULL
               AND t.respond_inbox_url IS NOT NULL
               AND t.respond_inbox_url <> ''
               AND rc.id = t.contact_id
               AND rc.respond_io_id IS NOT NULL
               AND rc.respond_io_id <> ''
               AND substring(t.respond_inbox_url FROM '[^/]+$') = rc.id
            """
        )


def downgrade() -> None:
    # Reverse direction: rewrite last segment back to the RespondContact.id when
    # it currently matches respond_io_id. Mirror of upgrade(); idempotent.
    for table in TARGET_TABLES:
        op.execute(
            f"""
            UPDATE {table} AS t
               SET respond_inbox_url = regexp_replace(t.respond_inbox_url, '[^/]+$', rc.id)
              FROM respond_contacts rc
             WHERE t.contact_id IS NOT NULL
               AND t.respond_inbox_url IS NOT NULL
               AND t.respond_inbox_url <> ''
               AND rc.id = t.contact_id
               AND rc.respond_io_id IS NOT NULL
               AND rc.respond_io_id <> ''
               AND substring(t.respond_inbox_url FROM '[^/]+$') = rc.respond_io_id
            """
        )
