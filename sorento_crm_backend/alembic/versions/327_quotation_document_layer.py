"""The quotation DOCUMENT layer, above the existing per-scope chain.

`project_quotations` has always BEEN a scope: it carries `scope_label`, its own outcome, and its
own version chain. The client needs one quotation carrying several scopes as tabs, so a document
table goes ABOVE it and every existing invariant is left alone - per-scope outcome, MAX(version_no)
as current, snapshot-at-quote-time lines, and every FK that points at a version.

The backfill is the interesting half. `document_id` must end up NOT NULL, and it is set in the
SAME revision as the insert that populates it: splitting them over two deploys leaves a window
where creating a quotation fails. Written as JOIN-based "set where it disagrees" rather than
"update where null" so a re-run corrects a previous partial run instead of skipping it.

Numbering: `document_numbering_rules` gains `company_id` and its unique key becomes
`(company_id, doc_type)`. `doc_type` alone was globally unique with no company column at all, so
SRT and MOCHA would have drawn from ONE counter and printed the same prefix - discovered only
after the numbers are on customer documents, which is far too late for a running series.

Revision ID: 327_quotation_document_layer
Revises: 326_attachments_entity_type_allow_project
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID


revision = "327_quotation_document_layer"
down_revision = "326_attachments_entity_type_allow_project"
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
    bind = op.get_bind()

    if not _has_table("project_quotation_documents"):
        op.create_table(
            "project_quotation_documents",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "project_id",
                UUID(as_uuid=False),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("document_no", sa.String(64), nullable=False),
            sa.Column("your_ref", sa.String(120), nullable=True),
            sa.Column("doc_date", sa.Date(), nullable=True),
            sa.Column(
                "recipient_party_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_parties.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("recipient_name_snapshot", sa.String(200), nullable=True),
            sa.Column("recipient_address_snapshot", sa.Text(), nullable=True),
            sa.Column("recipient_phone_snapshot", sa.String(200), nullable=True),
            sa.Column("attn_name", sa.String(120), nullable=True),
            sa.Column("subject_title", sa.Text(), nullable=True),
            sa.Column("cover_letter_html", sa.Text(), nullable=True),
            sa.Column("terms_html", sa.Text(), nullable=True),
            sa.Column("signatory_name", sa.String(120), nullable=True),
            sa.Column("signatory_phone", sa.String(60), nullable=True),
            sa.Column("created_by", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_project_quotation_documents_project", "project_quotation_documents", ["project_id"]
        )
        op.create_unique_constraint(
            "uq_project_quotation_documents_no",
            "project_quotation_documents",
            ["company_id", "document_no"],
        )

    if not _has_table("project_quotation_issues"):
        op.create_table(
            "project_quotation_issues",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "document_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_quotation_documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("issue_no", sa.Integer(), nullable=False),
            sa.Column("our_ref_text", sa.String(120), nullable=True),
            sa.Column("issued_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "issued_by",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("cover_letter_rendered", sa.Text(), nullable=True),
            sa.Column("terms_rendered", sa.Text(), nullable=True),
            sa.Column(
                "grand_total", sa.Numeric(15, 2), server_default="0", nullable=False
            ),
            sa.Column(
                "pdf_attachment_id",
                UUID(as_uuid=False),
                sa.ForeignKey("attachments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "xlsx_attachment_id",
                UUID(as_uuid=False),
                sa.ForeignKey("attachments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_unique_constraint(
            "uq_project_quotation_issues_no",
            "project_quotation_issues",
            ["document_id", "issue_no"],
        )

    if not _has_table("project_quotation_issue_scopes"):
        op.create_table(
            "project_quotation_issue_scopes",
            sa.Column("id", UUID(as_uuid=False), primary_key=True),
            sa.Column("company_id", UUID(as_uuid=False), nullable=True),
            sa.Column(
                "issue_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_quotation_issues.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "quotation_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_quotations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "version_id",
                UUID(as_uuid=False),
                sa.ForeignKey("project_quotation_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("scope_total", sa.Numeric(15, 2), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_unique_constraint(
            "uq_project_quotation_issue_scopes_scope",
            "project_quotation_issue_scopes",
            ["issue_id", "quotation_id"],
        )
        op.create_index(
            "ix_project_quotation_issue_scopes_version",
            "project_quotation_issue_scopes",
            ["version_id"],
        )

    # ------------------------------------------------------------------ scope columns
    if not _has_column("project_quotations", "document_id"):
        op.add_column(
            "project_quotations", sa.Column("document_id", UUID(as_uuid=False), nullable=True)
        )
        op.create_foreign_key(
            "fk_project_quotations_document",
            "project_quotations",
            "project_quotation_documents",
            ["document_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if not _has_column("project_quotations", "sort_order"):
        op.add_column(
            "project_quotations",
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        )

    # ------------------------------------------------------------------ line columns
    for name, column in (
        ("item_label", sa.Column("item_label", sa.String(8), nullable=True)),
        ("brand_snapshot", sa.Column("brand_snapshot", sa.String(100), nullable=True)),
        ("technical_spec", sa.Column("technical_spec", sa.Text(), nullable=True)),
        ("complete_set", sa.Column("complete_set", sa.String(100), nullable=True)),
        ("band_label", sa.Column("band_label", sa.String(150), nullable=True)),
        (
            "is_rate_only",
            sa.Column(
                "is_rate_only", sa.Boolean(), server_default="false", nullable=False
            ),
        ),
    ):
        if not _has_column("project_quotation_lines", name):
            op.add_column("project_quotation_lines", column)

    # ------------------------------------------------------------------ numbering per company
    if not _has_column("document_numbering_rules", "company_id"):
        op.add_column(
            "document_numbering_rules", sa.Column("company_id", UUID(as_uuid=False), nullable=True)
        )
        # Existing rules belong to the company that has been using them. Only one company was ever
        # live, so stamping Sorento is correct rather than a guess; a null would make the new
        # unique key treat every legacy rule as belonging to nobody.
        op.execute(
            text(
                "update document_numbering_rules set company_id = "
                "(select id from companies where code = 'SRT' limit 1) where company_id is null"
            )
        )
        op.execute(
            text(
                "alter table document_numbering_rules "
                "drop constraint if exists document_numbering_rules_doc_type_key"
            )
        )
        op.execute(
            text(
                "drop index if exists ix_document_numbering_rules_doc_type"
            )
        )
        op.create_index(
            "ix_document_numbering_rules_doc_type", "document_numbering_rules", ["doc_type"]
        )
        op.create_unique_constraint(
            "uq_document_numbering_rules_company_doc_type",
            "document_numbering_rules",
            ["company_id", "doc_type"],
        )

    # A rule per company that already has quotations, so the first document does not have to
    # invent its own number. `PRJQ-{year}-` is a starting point an admin can change in Setup.
    op.execute(
        text(
            """
            insert into document_numbering_rules
                (id, company_id, doc_type, enabled, prefix_template, number_digits,
                 next_value, start_value, reset_policy)
            select gen_random_uuid(), c.id, 'project_quotation', true, 'PRJQ-{year}-', 4, 1, 1,
                   'yearly'
            from companies c
            where not exists (
                select 1 from document_numbering_rules r
                where r.doc_type = 'project_quotation' and r.company_id = c.id
            )
            """
        )
    )

    # ------------------------------------------------------------------ backfill
    # One document per existing quotation: every current scope keeps its own letterhead, which is
    # the only reading that cannot change what anybody already quoted. Grouping several scopes of
    # one project into a shared document would silently merge quotations that were sent separately.
    #
    # `set where it disagrees` rather than `where null`: a half-finished previous run leaves rows
    # pointing at a document that was rolled back, and "where null" would skip exactly those.
    op.execute(
        text(
            """
            insert into project_quotation_documents
                (id, company_id, project_id, document_no, doc_date, recipient_party_id,
                 recipient_name_snapshot, recipient_address_snapshot, recipient_phone_snapshot,
                 subject_title, created_by, created_at, updated_at)
            select
                gen_random_uuid(),
                q.company_id,
                q.project_id,
                'Q-' || substr(replace(q.id::text, '-', ''), 1, 12),
                coalesce(v.issued_on, q.created_at::date),
                p.developer_party_id,
                party.name,
                party.address,
                party.phone,
                p.title,
                q.created_by,
                q.created_at,
                q.updated_at
            from project_quotations q
            join projects p on p.id = q.project_id
            left join project_parties party on party.id = p.developer_party_id
            left join (
                select quotation_id, min(issued_on) as issued_on
                from project_quotation_versions
                group by quotation_id
            ) v on v.quotation_id = q.id
            where q.document_id is null
               or not exists (
                   select 1 from project_quotation_documents d where d.id = q.document_id
               )
            """
        )
    )
    # The generated `document_no` carries the quotation id, so the join back needs no temp column.
    op.execute(
        text(
            """
            update project_quotations q
            set document_id = d.id
            from project_quotation_documents d
            where d.document_no = 'Q-' || substr(replace(q.id::text, '-', ''), 1, 12)
              and (q.document_id is distinct from d.id)
            """
        )
    )

    orphans = bind.execute(
        text("select count(*) from project_quotations where document_id is null")
    ).scalar()
    if orphans:
        raise RuntimeError(
            f"{orphans} project_quotations rows still have no document after the backfill; "
            "refusing to set the column NOT NULL with the data in that state."
        )

    op.alter_column("project_quotations", "document_id", nullable=False)


def downgrade() -> None:
    op.alter_column("project_quotations", "document_id", nullable=True)
    op.drop_constraint(
        "fk_project_quotations_document", "project_quotations", type_="foreignkey"
    )
    op.drop_column("project_quotations", "document_id")
    op.drop_column("project_quotations", "sort_order")

    for name in (
        "item_label",
        "brand_snapshot",
        "technical_spec",
        "complete_set",
        "band_label",
        "is_rate_only",
    ):
        op.drop_column("project_quotation_lines", name)

    op.drop_table("project_quotation_issue_scopes")
    op.drop_table("project_quotation_issues")
    op.drop_table("project_quotation_documents")

    op.execute(text("delete from document_numbering_rules where doc_type = 'project_quotation'"))
    op.drop_constraint(
        "uq_document_numbering_rules_company_doc_type",
        "document_numbering_rules",
        type_="unique",
    )
    op.drop_column("document_numbering_rules", "company_id")
