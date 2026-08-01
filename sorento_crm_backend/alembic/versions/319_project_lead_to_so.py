"""319 customer PO to sales order (phase 2)

Sixteen module tables plus the lead changes phase 2 needs. Nothing is added to a CORE
table: `sales_orders` and `sales_order_lines` stay ignorant of projects (finding G5), and
the link runs from `project_sales_orders.so_id` instead.

`project_leads.customer_id` becomes NULLABLE and changes meaning to the BUYER (D6). A BCI
sighting has no buyer at all -- the trading house only exists once a contractor is awarded
-- and the informant who told us is recorded separately because BCI is not a debtor.

Revision ID: 319_project_lead_to_so
Revises: 318_complaint_project
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "319_project_lead_to_so"
down_revision = "318_complaint_project"
branch_labels = None
depends_on = None

LEAD_COLUMNS = (
    # who told us. Never written to `customers`: BCI is a data source, not a debtor.
    ("informant_source", sa.String(length=32)),
    ("informant_ref", sa.String(length=180)),
    ("informant_party_id", postgresql.UUID(as_uuid=False)),
    ("informant_contact_name", sa.String(length=180)),
    # the acceptance handshake (D7). Assignment alone never means ownership.
    ("acceptance_state", sa.String(length=24)),
    ("assigned_at", sa.DateTime()),
    ("accepted_at", sa.DateTime()),
    ("declined_reason", sa.Text()),
    ("declined_at", sa.DateTime()),
)


def upgrade() -> None:
    op.create_table(
        "customer_pos",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("po_number", sa.String(length=120), nullable=False),
        sa.Column("po_date", sa.Date(), nullable=True),
        sa.Column("term_days", sa.Integer(), nullable=True),
        sa.Column("sales_person", sa.String(length=120), nullable=True),
        sa.Column("customer_order_ref", sa.String(length=180), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("admin_ref", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("supersedes_po_number", sa.String(length=120), nullable=True),
        sa.Column("superseded_by_po_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_pos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("countersigned_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("countersigned_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("company_id", "project_id", "po_number", name="uq_customer_pos_project_number"),
    )
    op.create_index("ix_customer_pos_company_id", "customer_pos", ["company_id"])
    op.create_index("ix_customer_pos_project", "customer_pos", ["project_id"])
    op.create_index("ix_customer_pos_status", "customer_pos", ["status"])

    op.create_table(
        "customer_po_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_pos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_filename", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extracted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_model", sa.String(length=80), nullable=True),
        sa.Column("extraction_tokens_in", sa.Integer(), nullable=True),
        sa.Column("extraction_tokens_out", sa.Integer(), nullable=True),
        sa.Column("arithmetic_passed", sa.Integer(), nullable=True),
        sa.Column("arithmetic_total", sa.Integer(), nullable=True),
        sa.Column("extracted_total", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("confirmed_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("customer_po_id", "version_no", name="uq_customer_po_versions_no"),
    )
    op.create_index("ix_customer_po_versions_company_id", "customer_po_versions", ["company_id"])

    op.create_table(
        "customer_po_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("po_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_po_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("stock_code_raw", sa.String(length=180), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=True),
        sa.Column("qty", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("uom_raw", sa.String(length=40), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=15, scale=5), nullable=True),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("is_cancelled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("resolved_product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_source", sa.String(length=32), nullable=True),
        sa.Column("arithmetic_ok", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("po_version_id", "line_no", name="uq_customer_po_lines_no"),
    )
    op.create_index("ix_customer_po_lines_company_id", "customer_po_lines", ["company_id"])
    op.create_index("ix_customer_po_lines_version", "customer_po_lines", ["po_version_id"])

    op.create_table(
        "customer_po_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("po_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_po_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dedup_key", sa.String(length=180), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("crop_attachment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("written_date", sa.String(length=40), nullable=True),
        sa.Column("refers_to_lines", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("interpretation", sa.String(length=64), nullable=True),
        sa.Column("interpretation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("state", sa.String(length=16), server_default=sa.text("'proposed'"), nullable=False),
        sa.Column("actioned_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actioned_at", sa.DateTime(), nullable=True),
        sa.Column("action_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("po_version_id", "dedup_key", name="uq_po_annotations_dedup"),
    )
    op.create_index("ix_customer_po_annotations_company_id", "customer_po_annotations", ["company_id"])

    op.create_table(
        "delivery_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_pos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issuer_party_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_parties.id", ondelete="SET NULL"), nullable=True),
        sa.Column("label", sa.String(length=180), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_delivery_schedules_po", "delivery_schedules", ["customer_po_id"])
    op.create_index("ix_delivery_schedules_company_id", "delivery_schedules", ["company_id"])

    op.create_table(
        "delivery_schedule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("delivery_schedule_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("delivery_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("revision_label", sa.String(length=80), nullable=True),
        sa.Column("po_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_po_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_filename", sa.Text(), nullable=True),
        sa.Column("schedule_date", sa.Date(), nullable=True),
        sa.Column("extracted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_model", sa.String(length=80), nullable=True),
        sa.Column("reconciled_columns", sa.Integer(), nullable=True),
        sa.Column("total_columns", sa.Integer(), nullable=True),
        sa.Column("reconciliation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confirmed_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("delivery_schedule_id", "version_no", name="uq_schedule_versions_no"),
    )
    op.create_index("ix_delivery_schedule_versions_company_id", "delivery_schedule_versions", ["company_id"])

    op.create_table(
        "project_delivery_phases",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area_group", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=180), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("source_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("delivery_schedule_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("project_id", "area_group", "sequence", name="uq_delivery_phase_identity"),
    )
    op.create_index("ix_project_delivery_phases_company_id", "project_delivery_phases", ["company_id"])
    op.create_index("ix_delivery_phases_project", "project_delivery_phases", ["project_id"])

    op.create_table(
        "delivery_schedule_cells",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("delivery_schedule_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_delivery_phases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("customer_code_raw", sa.String(length=180), nullable=True),
        sa.Column("qty", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_schedule_cells_phase", "delivery_schedule_cells", ["phase_id"])
    op.create_index("ix_schedule_cells_version", "delivery_schedule_cells", ["version_id"])
    op.create_index("ix_delivery_schedule_cells_company_id", "delivery_schedule_cells", ["company_id"])

    op.create_table(
        "customer_item_code_map",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_code", sa.String(length=180), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("confirmed_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("company_id", "customer_id", "customer_code", name="uq_customer_code_map"),
    )
    op.create_index("ix_customer_item_code_map_company_id", "customer_item_code_map", ["company_id"])

    op.create_table(
        "project_sales_orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_pos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schedule_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("delivery_schedule_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("so_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("sales_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("area_group", sa.String(length=80), nullable=True),
        sa.Column("provisional_ref", sa.String(length=80), nullable=False),
        sa.Column("autocount_doc_no", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=24), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("is_pre_order", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_sponsorship", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sponsorship_form_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("purchase_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grouping_origin", sa.String(length=32), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("published_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("company_id", "provisional_ref", name="uq_project_so_provisional_ref"),
    )
    op.create_index("ix_project_so_status", "project_sales_orders", ["status"])
    op.create_index("ix_project_sales_orders_company_id", "project_sales_orders", ["company_id"])
    op.create_index("ix_project_so_project", "project_sales_orders", ["project_id"])

    op.create_table(
        "project_sales_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_sales_order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("qty", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("uom", sa.String(length=40), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=15, scale=5), server_default=sa.text("0"), nullable=False),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), server_default=sa.text("0"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("phase_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_delivery_phases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_po_line_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_po_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quotation_line_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_quotation_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stock_location", sa.String(length=80), nullable=True),
        sa.Column("explosion_source", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_project_so_lines_order", "project_sales_order_lines", ["project_sales_order_id"])
    op.create_index("ix_project_sales_order_lines_company_id", "project_sales_order_lines", ["company_id"])

    op.create_table(
        "so_draft_findings",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_sales_order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_order_lines.id", ondelete="CASCADE"), nullable=True),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("acknowledged_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_so_draft_findings_company_id", "so_draft_findings", ["company_id"])
    op.create_index("ix_so_findings_order", "so_draft_findings", ["project_sales_order_id"])
    op.create_index("ix_so_findings_severity", "so_draft_findings", ["severity"])

    op.create_table(
        "order_change_notices",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("ocn_number", sa.String(length=64), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_po_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customer_pos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_sales_order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_document_kind", sa.String(length=32), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("change_table_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approver_id", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
        sa.UniqueConstraint("company_id", "ocn_number", name="uq_ocn_number"),
    )
    op.create_index("ix_order_change_notices_company_id", "order_change_notices", ["company_id"])

    op.create_table(
        "so_amendments",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_sales_order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ocn_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("order_change_notices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_version_kind", sa.String(length=32), nullable=True),
        sa.Column("from_version_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("to_version_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("verb_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'proposed'"), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_so_amendments_company_id", "so_amendments", ["company_id"])
    op.create_index("ix_so_amendments_order", "so_amendments", ["project_sales_order_id"])

    op.create_table(
        "order_inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("project_sales_order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amendment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("so_amendments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(length=16), server_default=sa.text("'raised'"), nullable=False),
        sa.Column("raised_by", sa.String(length=100), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raised_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_order_inquiries_order", "order_inquiries", ["project_sales_order_id"])
    op.create_index("ix_order_inquiries_company_id", "order_inquiries", ["company_id"])

    op.create_table(
        "order_inquiry_rows",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, primary_key=True),
        sa.Column("order_inquiry_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("order_inquiries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("so_line_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("project_sales_order_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_code", sa.String(length=120), nullable=True),
        sa.Column("qty", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("stock_location", sa.String(length=80), nullable=True),
        sa.Column("verb", sa.String(length=32), nullable=False),
        sa.Column("spo_ref", sa.String(length=80), nullable=True),
        sa.Column("covered_by", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=16), server_default=sa.text("'raised'"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True),
    )
    op.create_index("ix_order_inquiry_rows_company_id", "order_inquiry_rows", ["company_id"])
    op.create_index("ix_order_inquiry_rows_inquiry", "order_inquiry_rows", ["order_inquiry_id"])

    # --- leads: nullable buyer, informant, acceptance handshake -------------------
    op.alter_column("project_leads", "customer_id", existing_type=postgresql.UUID(as_uuid=False), nullable=True)
    for name, coltype in LEAD_COLUMNS:
        op.add_column("project_leads", sa.Column(name, coltype, nullable=True))
    op.create_foreign_key(
        "fk_project_leads_informant_party", "project_leads", "project_parties",
        ["informant_party_id"], ["id"], ondelete="SET NULL",
    )
    # Existing rows were all assigned by fiat under the old model, so they are accepted:
    # backfilling them as awaiting-acceptance would raise a clock on historical leads.
    op.execute("UPDATE project_leads SET acceptance_state = 'accepted' WHERE acceptance_state IS NULL")

    # `projects.admin_ref` is the PS filing reference (D24), searchable, not an identity.
    op.add_column("projects", sa.Column("admin_ref", sa.String(length=64), nullable=True))
    op.create_index("ix_projects_admin_ref", "projects", ["admin_ref"])

    # AR outstanding, ingested from AutoCount (D23). Without it the credit warning can only
    # compare an order value against a limit, which ignores what the customer already owes.
    op.add_column("customers", sa.Column("ar_outstanding", sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column("customers", sa.Column("ar_ageing_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("customers", sa.Column("ar_as_of", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "ar_as_of")
    op.drop_column("customers", "ar_ageing_json")
    op.drop_column("customers", "ar_outstanding")
    op.drop_index("ix_projects_admin_ref", table_name="projects")
    op.drop_column("projects", "admin_ref")
    op.drop_constraint("fk_project_leads_informant_party", "project_leads", type_="foreignkey")
    for name, _ in reversed(LEAD_COLUMNS):
        op.drop_column("project_leads", name)
    # customer_id stays nullable: re-tightening it would fail on any lead registered
    # without a buyer, which is the normal case this migration exists to allow.
    for table in (
        "order_inquiry_rows", "order_inquiries", "so_amendments", "order_change_notices",
        "so_draft_findings", "project_sales_order_lines", "project_sales_orders",
        "customer_item_code_map", "delivery_schedule_cells", "project_delivery_phases",
        "delivery_schedule_versions", "delivery_schedules", "customer_po_annotations",
        "customer_po_lines", "customer_po_versions", "customer_pos",
    ):
        op.drop_table(table)
