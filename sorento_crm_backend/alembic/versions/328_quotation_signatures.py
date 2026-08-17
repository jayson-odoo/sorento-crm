"""Signatures on both sides of a quotation issue, and the acceptance it records.

Both sides sign (client decision, 2026-08-04): the project owner before the quotation goes out,
and the customer to accept it. Each signature is a row rather than a column pair on the issue,
because each carries its own metadata and because a user's reusable signature is the same shape
with no issue behind it.

`sign_token` is the tokenised counter-sign link. Unique so a lookup cannot be ambiguous, and
nullable because an issue has no token until somebody sends it.

Revision ID: 328_quotation_signatures
Revises: 327_quotation_document_layer
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID


revision = "328_quotation_signatures"
down_revision = "327_quotation_document_layer"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_name = :t and column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            text("select 1 from information_schema.tables where table_name = :t"), {"t": table}
        ).scalar()
    )


def upgrade() -> None:
    if not _has_table("quotation_signatures"):
        op.create_table(
            "quotation_signatures",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column("owner_kind", sa.String(16), nullable=False),
            sa.Column(
                "user_id",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("signer_name", sa.String(200), nullable=True),
            sa.Column("mode", sa.String(16), server_default="draw", nullable=False),
            sa.Column(
                "image_attachment_id",
                UUID(as_uuid=False),
                sa.ForeignKey("attachments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("image_data_uri", sa.Text(), nullable=True),
            sa.Column("signed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("gps_lat", sa.Numeric(10, 7), nullable=True),
            sa.Column("gps_lng", sa.Numeric(10, 7), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_quotation_signatures_user", "quotation_signatures", ["user_id", "owner_kind"]
        )

    for name, column in (
        (
            "sorento_signature_id",
            sa.Column("sorento_signature_id", UUID(as_uuid=False), nullable=True),
        ),
        (
            "customer_signature_id",
            sa.Column("customer_signature_id", UUID(as_uuid=False), nullable=True),
        ),
        ("accepted_at", sa.Column("accepted_at", sa.DateTime(), nullable=True)),
        (
            "signed_pdf_attachment_id",
            sa.Column("signed_pdf_attachment_id", UUID(as_uuid=False), nullable=True),
        ),
        ("sign_token", sa.Column("sign_token", sa.String(255), nullable=True)),
        (
            "sign_token_expires_at",
            sa.Column("sign_token_expires_at", sa.DateTime(), nullable=True),
        ),
    ):
        if not _has_column("project_quotation_issues", name):
            op.add_column("project_quotation_issues", column)

    if not _has_column("project_quotation_documents", "signatory_signature_id"):
        op.add_column(
            "project_quotation_documents",
            sa.Column("signatory_signature_id", UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_project_quotation_documents_signature",
            "project_quotation_documents",
            "quotation_signatures",
            ["signatory_signature_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Added after the columns so a re-run of a partial upgrade does not trip over them.
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            text(
                "select conname from pg_constraint "
                "where conrelid = 'project_quotation_issues'::regclass"
            )
        )
    }
    if "fk_project_quotation_issues_sorento_signature" not in existing:
        op.create_foreign_key(
            "fk_project_quotation_issues_sorento_signature",
            "project_quotation_issues",
            "quotation_signatures",
            ["sorento_signature_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "fk_project_quotation_issues_customer_signature" not in existing:
        op.create_foreign_key(
            "fk_project_quotation_issues_customer_signature",
            "project_quotation_issues",
            "quotation_signatures",
            ["customer_signature_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "fk_project_quotation_issues_signed_pdf" not in existing:
        op.create_foreign_key(
            "fk_project_quotation_issues_signed_pdf",
            "project_quotation_issues",
            "attachments",
            ["signed_pdf_attachment_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "uq_project_quotation_issues_sign_token" not in existing:
        op.create_unique_constraint(
            "uq_project_quotation_issues_sign_token",
            "project_quotation_issues",
            ["sign_token"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_quotation_documents_signature",
        "project_quotation_documents",
        type_="foreignkey",
    )
    op.drop_column("project_quotation_documents", "signatory_signature_id")
    op.drop_constraint(
        "uq_project_quotation_issues_sign_token", "project_quotation_issues", type_="unique"
    )
    for name in (
        "fk_project_quotation_issues_signed_pdf",
        "fk_project_quotation_issues_customer_signature",
        "fk_project_quotation_issues_sorento_signature",
    ):
        op.drop_constraint(name, "project_quotation_issues", type_="foreignkey")
    for name in (
        "sign_token_expires_at",
        "sign_token",
        "signed_pdf_attachment_id",
        "accepted_at",
        "customer_signature_id",
        "sorento_signature_id",
    ):
        op.drop_column("project_quotation_issues", name)
    op.drop_table("quotation_signatures")
