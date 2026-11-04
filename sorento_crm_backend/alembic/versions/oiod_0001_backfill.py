"""OI-ONE-DELIVERY-DATE: an order inquiry row's date becomes its SO line's date.

Data only, no DDL on an existing table. For every order inquiry row that is not cancelled and
whose SO line date (the core ``sales_order_lines.required_date``, else the project mirror
line's ``delivery_date``) is set and differs from the row's own ``delivery_date``:

    previous_delivery_date := the old delivery_date   (the Was)
    delivery_date          := the SO line date

Rows that already match, rows with no SO line and rows whose line has no date are untouched
(2030-01-01 is a date like any other). Several rows on one line each take the line's date and
keep their own old date as the Was. The raw UPDATE writes no audit row, planning change or ack
change, and nothing here sends an email (card Q2 a).

Each changed row is first logged in ``projects.oi_delivery_date_backfill`` (row id, old
delivery date, old previous date) so the downgrade restores them exactly and drops the log.

Revision ID: oiod_0001_backfill
Revises: ssv2_0001_spec_sheets
"""
from alembic import op


revision = "oiod_0001_backfill"
down_revision = "ssv2_0001_spec_sheets"
branch_labels = None
depends_on = None

#: The SO line date of every live row that differs from its own date.
_DIFFERING = """
    SELECT r.id AS row_id,
           r.delivery_date AS old_delivery_date,
           r.previous_delivery_date AS old_previous_delivery_date,
           COALESCE(c.required_date, m.delivery_date) AS line_date
    FROM projects.order_inquiry_rows r
    JOIN projects.sales_order_lines m ON m.id = r.so_line_id
    LEFT JOIN public.sales_order_lines c ON c.id = m.core_sales_order_line_id
    WHERE r.state <> 'cancelled'
      AND COALESCE(c.required_date, m.delivery_date) IS NOT NULL
      AND COALESCE(c.required_date, m.delivery_date) IS DISTINCT FROM r.delivery_date
"""


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS projects.oi_delivery_date_backfill ("
        "row_id uuid PRIMARY KEY, "
        "old_delivery_date date, "
        "old_previous_delivery_date date)"
    )
    op.execute(
        "INSERT INTO projects.oi_delivery_date_backfill "
        "(row_id, old_delivery_date, old_previous_delivery_date) "
        f"SELECT d.row_id, d.old_delivery_date, d.old_previous_delivery_date FROM ({_DIFFERING}) d "
        "ON CONFLICT (row_id) DO NOTHING"
    )
    op.execute(
        "UPDATE projects.order_inquiry_rows r "
        "SET previous_delivery_date = d.old_delivery_date, delivery_date = d.line_date "
        f"FROM ({_DIFFERING}) d WHERE r.id = d.row_id"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE projects.order_inquiry_rows r "
        "SET delivery_date = b.old_delivery_date, "
        "previous_delivery_date = b.old_previous_delivery_date "
        "FROM projects.oi_delivery_date_backfill b WHERE r.id = b.row_id"
    )
    op.execute("DROP TABLE IF EXISTS projects.oi_delivery_date_backfill")
