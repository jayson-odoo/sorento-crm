"""strip the price_tag_request grant out of every contact access type

D61a of PLAN-price-tag-request, section 14. Price Tag Request must reach nobody
on the day the branch deploys.

``ptag_0001`` used to write ``["price_tag_request", "stock_inquiry"]`` onto every
``contact_access_types`` row whose code contains "dealer". That statement now
writes ``["stock_inquiry"]`` alone, which covers a fresh database - but the
databases that already ran the earlier version still carry the grant. This walks
it back, so both land in the same state.

Idempotent by construction: it removes a key from a jsonb array with the ``-``
operator, and after it runs its own WHERE matches nothing.

Revision ID: ptag_0003
Revises: ptag_0002
Create Date: 2026-08-30
"""
import sqlalchemy as sa
from alembic import op


revision = "ptag_0003"
down_revision = "ptag_0002"
branch_labels = None
depends_on = None

# Kept as a module constant so the test asserts the statement production runs
# rather than a retyped copy of it. ``@>`` rather than the ``?`` containment
# operator: ``?`` is a bind-parameter marker in more than one driver, and this
# string travels through SQLAlchemy's text() on its way to psycopg.
STRIP_SQL = """
    UPDATE contact_access_types
    SET portal_form_types = portal_form_types - 'price_tag_request'
    WHERE jsonb_typeof(portal_form_types) = 'array'
      AND portal_form_types @> '["price_tag_request"]'::jsonb
"""


def upgrade() -> None:
    op.get_bind().execute(sa.text(STRIP_SQL))


def downgrade() -> None:
    # Deliberately nothing.
    #
    # A grant is an admin decision, made on the Contact Access Types screen by
    # somebody who chose which access types may see the form. A downgrade that
    # re-granted price_tag_request would be inventing that decision, and it would
    # invent it for whichever rows a LIKE pattern happened to match - which is
    # exactly the behaviour D61a removed. Downgrading past this revision leaves
    # the grants as the admins left them.
    pass
