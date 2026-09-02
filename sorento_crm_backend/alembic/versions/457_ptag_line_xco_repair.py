"""price_tag_request_lines: repair lines that point at another company's product row

Root cause: products are cloned per company (Sorento and Mocha share
`product_code`s), and before the picker's company-scope fix (#485,
`6d147c0a7`), a two-company portal contact could put the OTHER company's
product row onto a request. `GET /dealer-kit/products/{id}/tag-data` then
404s under the request's own company scope, and `RequestTagDesigner` shows
the resolution as a stack of "Product not found" toasts, one per attempt.

The fix: for every line whose product's `company_id` differs from its
request's `company_id`, repoint it at the sibling row with the same
`product_code` in the request's own company - the row the user actually
meant. A line with no same-code row in the request's company is left alone;
there is nothing to repoint it to, and this migration does not delete lines.

The dev DB already carries two such lines (PT-202608-0002 / -0003, both
pointing at a Mocha `CBF66406` row from a Sorento request) and they were
repaired there BY HAND on 2 Sep 2026, ahead of this migration - do not run
this migration against the shared dev DB; its `alembic_version` is untouched.
This migration is for prod and any other environment the hand repair never
touched.

Replay-safe by construction: the `UPDATE ... FROM` only ever matches a line
whose product's company still disagrees with its request's, so once a line
is repaired the same run (or a later one) no longer selects it. No downgrade
is meaningful - there is no record of which company a line used to point at,
so `downgrade()` is a no-op.

Revision ID: 457_ptag_line_xco_repair
Revises: 456_page_draft_doc
Create Date: 2026-09-02 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "457_ptag_line_xco_repair"
down_revision = "456_page_draft_doc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    mismatched = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM price_tag_request_lines AS l
            JOIN products AS p ON p.id = l.product_id
            JOIN price_tag_requests AS r ON r.id = l.request_id
            WHERE p.company_id <> r.company_id
            """
        )
    ).scalar()

    result = bind.execute(
        sa.text(
            """
            UPDATE price_tag_request_lines AS l
            SET product_id = p2.id
            FROM products AS p, products AS p2, price_tag_requests AS r
            WHERE l.product_id = p.id
              AND r.id = l.request_id
              AND p.company_id <> r.company_id
              AND p2.product_code = p.product_code
              AND p2.company_id = r.company_id
            """
        )
    )

    repaired = result.rowcount or 0
    unfixable = (mismatched or 0) - repaired
    print(
        f"457_ptag_line_xco_repair: {mismatched} line(s) pointed at another "
        f"company's product; {repaired} repointed to the request company's own "
        f"row, {unfixable} left unrepaired (no matching product_code in that "
        f"company)."
    )


def downgrade() -> None:
    # No-op: the repair does not record which company a line used to point
    # at, so there is nothing to reverse to.
    pass
