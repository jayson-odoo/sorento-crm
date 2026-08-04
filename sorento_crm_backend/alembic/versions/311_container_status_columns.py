"""Container status: clearance columns on inbound_shipments + the observation ledger.

`Container Status 2026.xlsx` is maintained by hand and holds the dates n8n needs to
answer "what's the ETA delay". One sheet row IS one packing list - the codebase
already treats the container number as the shipment's identity - so the 25 operational
fields land as flat columns on `inbound_shipments` rather than in a milestone child
table (decisions D1, D3). Revision history comes free from `__audit_track__` on the
model, so there is no revisions table either (D5).

Every column is nullable with no server default, so existing rows are untouched by
this DDL and nothing existing reads them yet.

`shipment_tracking_observations` is the other half: append-only, integration-only.
A liner or CIDB adapter records what it SAW, and never writes to the shipment row.
Paired `*_observed` columns were rejected because they overwrite on each poll, which
destroys the timing evidence - and the timing evidence is the entire justification
for the validation period before the Excel is retired (D7).

Two indexes carry real query load:
  * `shipping_container_number` - the importer matches on it across EVERY shipment
    status, so the existing status-scoped indexes do not help it.
  * `eta_delay_date` - "which containers are still open" drives the daily tracking
    poll (~77 containers).

Revision ID: 311_container_status_columns
Revises: 310_form_sla_skip_stage
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "311_container_status_columns"
down_revision = "310_form_sla_skip_stage"
branch_labels = None
depends_on = None


# (name, type). Ordered as the sheet reads: parties, then the milestone chain,
# then the four fields the sheet keeps but nobody maintains.
_TEXT_COLUMNS = [
    ("loc", sa.String(50)),
    ("liner_code", sa.String(50)),
    ("china_forwarder", sa.String(100)),
    ("malaysia_forwarder", sa.String(100)),
    ("consignee", sa.String(150)),
    ("stacked", sa.String(50)),
    ("delivery_warehouse", sa.String(150)),
    ("coa_permit_no", sa.String(100)),
    ("source_sheet", sa.String(100)),
]

_DATE_COLUMNS = [
    "loading_date",
    "etc_date",
    "etd_date",
    "eta_date",
    "eta_delay_date",
    "inspection_date",
    "approval_date",
    "gatepass_date",
    "warehouse_arrival_date",
    "informed_collection_date",
    "collection_date",
    # Round-trip only. Fill rates across the 407 real containers: 6 / 4 / 4 / 4.
    "ata_date",
    "ori_doc_received_date",
    "k1_submission_date",
    "yard_arrival_date",
]


def upgrade() -> None:
    for name, type_ in _TEXT_COLUMNS:
        op.add_column("inbound_shipments", sa.Column(name, type_, nullable=True))
    for name in _DATE_COLUMNS:
        op.add_column("inbound_shipments", sa.Column(name, sa.Date(), nullable=True))
    op.add_column(
        "inbound_shipments",
        sa.Column("free_days_available", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_inbound_shipments_container_number",
        "inbound_shipments",
        ["shipping_container_number"],
    )
    op.create_index(
        "ix_inbound_shipments_eta_delay_date",
        "inbound_shipments",
        ["eta_delay_date"],
    )

    op.create_table(
        "shipment_tracking_observations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "shipment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("inbound_shipments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(60), nullable=False),
        sa.Column("observed_value", sa.Text(), nullable=True),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Matches CompanyScopedMixin exactly: plain FK, nullable, indexed. The
        # auto-stamp on insert fills it; migration 305's NOT NULL flip covers the
        # tables that existed then, and this one starts empty.
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_shipment_tracking_observations_company_id",
        "shipment_tracking_observations",
        ["company_id"],
    )
    op.create_index(
        "ix_shipment_tracking_obs_shipment_field",
        "shipment_tracking_observations",
        ["shipment_id", "field_key", "fetched_at"],
    )
    op.create_index(
        "ix_shipment_tracking_obs_source",
        "shipment_tracking_observations",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shipment_tracking_observations_company_id",
        table_name="shipment_tracking_observations",
    )
    op.drop_index("ix_shipment_tracking_obs_source", table_name="shipment_tracking_observations")
    op.drop_index(
        "ix_shipment_tracking_obs_shipment_field",
        table_name="shipment_tracking_observations",
    )
    op.drop_table("shipment_tracking_observations")

    op.drop_index("ix_inbound_shipments_eta_delay_date", table_name="inbound_shipments")
    op.drop_index("ix_inbound_shipments_container_number", table_name="inbound_shipments")

    op.drop_column("inbound_shipments", "free_days_available")
    for name in reversed(_DATE_COLUMNS):
        op.drop_column("inbound_shipments", name)
    for name, _type in reversed(_TEXT_COLUMNS):
        op.drop_column("inbound_shipments", name)
