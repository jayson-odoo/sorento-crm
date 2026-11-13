"""Price tag request line: one product may sit on a request any number of times.

PRICETAG-ALA-CARTE (documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md AC-14):
a product line's package is its combo_id (null = ala carte), and the same product may be asked for
on several lines, whatever the packages. The request + product unique is dropped with no
replacement; lines are told apart by their own id. Idempotent (`IF EXISTS`).

Revision ID: ptag_0023_line_package
Revises: prr_0001_si_npa_project
"""
from __future__ import annotations

from alembic import op

revision = "ptag_0023_line_package"
down_revision = "prr_0001_si_npa_project"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE price_tag_request_lines DROP CONSTRAINT IF EXISTS uq_ptag_line_request_product"
    )


def downgrade() -> None:
    # Refused, by name, while any request holds one product twice: the old unique cannot hold
    # until those lines are merged by hand.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM price_tag_request_lines
                WHERE product_id IS NOT NULL
                GROUP BY request_id, product_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot re-add uq_ptag_line_request_product: a price tag request '
                    'holds one product twice (duplicate lines). Merge those lines first.';
            END IF;
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE price_tag_request_lines ADD CONSTRAINT uq_ptag_line_request_product "
        "UNIQUE (request_id, product_id)"
    )
