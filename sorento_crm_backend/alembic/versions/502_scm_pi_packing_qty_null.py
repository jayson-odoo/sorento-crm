"""A packing row (or line) with no quantity is still a packing row (or line).

S2 follow-up (captain ruling 9 Sep): the Jinbaichuan sheet's container-summary row
(`家豪拼柜41个盆`, "jiahao's consolidated container, 41 basins") states a total CBM
(1.72) and no quantity at all - a code/description with SOME packing figure but no
qty is still a line/packing row (qty NULL), never dropped and never invented from the
row's own free text. Both `proforma_invoice_line.qty` and `proforma_invoice_packing_
line.qty` flip nullable to allow it.

Revision ID: 502_scm_pi_packing_qty_null
Revises: 501_scm_pi_packing_lines
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "502_scm_pi_packing_qty_null"
down_revision = "501_scm_pi_packing_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("proforma_invoice_line", "qty", nullable=True, schema="scm")
    op.alter_column("proforma_invoice_packing_line", "qty", nullable=True, schema="scm")


def downgrade() -> None:
    op.alter_column("proforma_invoice_packing_line", "qty", nullable=False, schema="scm")
    op.alter_column("proforma_invoice_line", "qty", nullable=False, schema="scm")
