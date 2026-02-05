"""Add order tracking columns to orders table

Revision ID: 017_add_order_tracking_columns
Revises: 016_add_from_time_duration
Create Date: 2026-01-28 00:40:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017_add_order_tracking_columns'
down_revision = '016_add_from_time_duration'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if 'orders' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('orders')}

    new_columns = [
        sa.Column('created_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('debtor_code', sa.String(length=100), nullable=True),
        sa.Column('debtor_name', sa.String(length=255), nullable=True),
        sa.Column('agent', sa.String(length=100), nullable=True),
        sa.Column('is_cancelled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('remarks_cs', sa.Text(), nullable=True),
        sa.Column('order_type', sa.String(length=50), nullable=True),
        sa.Column('delivery_time', sa.String(length=20), nullable=True),
        sa.Column('checker', sa.String(length=100), nullable=True),
        sa.Column('transporter', sa.String(length=100), nullable=True),
        sa.Column('driver_name', sa.String(length=100), nullable=True),
        sa.Column('lorry_plate', sa.String(length=50), nullable=True),
        sa.Column('customer_ref', sa.String(length=255), nullable=True),
        sa.Column('delivery_remarks_cs', sa.Text(), nullable=True),
        sa.Column('delivery_remarks', sa.Text(), nullable=True),
        sa.Column('salesman', sa.String(length=100), nullable=True),
        sa.Column('trips', sa.Integer(), nullable=True),
        sa.Column('warehouse', sa.String(length=50), nullable=True),
        sa.Column('delivery_days', sa.Integer(), nullable=True),
        sa.Column('kpi_warning', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    ]

    for column in new_columns:
        if column.name not in columns:
            op.add_column('orders', column)

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('orders')}
    if 'ix_orders_debtor_code' not in existing_indexes:
        op.create_index('ix_orders_debtor_code', 'orders', ['debtor_code'])
    if 'ix_orders_kpi_warning' not in existing_indexes:
        op.create_index('ix_orders_kpi_warning', 'orders', ['kpi_warning'])
    if 'ix_orders_is_cancelled' not in existing_indexes:
        op.create_index('ix_orders_is_cancelled', 'orders', ['is_cancelled'])


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if 'orders' not in inspector.get_table_names():
        return

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('orders')}
    if 'ix_orders_is_cancelled' in existing_indexes:
        op.drop_index('ix_orders_is_cancelled', table_name='orders')
    if 'ix_orders_kpi_warning' in existing_indexes:
        op.drop_index('ix_orders_kpi_warning', table_name='orders')
    if 'ix_orders_debtor_code' in existing_indexes:
        op.drop_index('ix_orders_debtor_code', table_name='orders')

    columns = {col['name'] for col in inspector.get_columns('orders')}
    drop_columns = [
        'kpi_warning',
        'delivery_days',
        'warehouse',
        'trips',
        'salesman',
        'delivery_remarks',
        'delivery_remarks_cs',
        'customer_ref',
        'lorry_plate',
        'driver_name',
        'transporter',
        'checker',
        'delivery_time',
        'order_type',
        'remarks_cs',
        'is_cancelled',
        'agent',
        'debtor_name',
        'debtor_code',
        'created_time',
    ]
    for column_name in drop_columns:
        if column_name in columns:
            op.drop_column('orders', column_name)
