"""Add respond_io_id to respond_contacts to store Respond.io contact id for inbox URL.

Revision ID: 079_respond_contacts_id
Revises: 078_total_project_value_text
Create Date: 2026-02-21

Stores the contact id from Respond.io (e.g. 386900418) so we can link to
https://app.respond.io/space/{space_id}/inbox/{respond_io_id}.
"""
from alembic import op
import sqlalchemy as sa


revision = "079_respond_contacts_id"
down_revision = "078_total_project_value_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "respond_contacts",
        sa.Column("respond_io_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_respond_contacts_respond_io_id",
        "respond_contacts",
        ["respond_io_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_respond_contacts_respond_io_id", table_name="respond_contacts")
    op.drop_column("respond_contacts", "respond_io_id")
