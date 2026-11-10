"""PROJECT-PARTY-ROLES: project party roles become the editable lookup set ``project_party_role``.

Owner rulings 10 Nov 2026 (card documentation/plans/project-sales/CARD-project-party-roles-10nov.md):

* ``lookup_options.allows_many``: "many parties allowed" per role (several trading houses);
* seed the set with today's eight roles, same keys and labels, many for trading house,
  subcontractor and tender party;
* backfill ``projects.party_links`` from ``sales_profile.architect_party_id`` /
  ``main_contractor_party_id`` (architect and main contractor become ordinary roles). The two
  columns stay: dropping them is destructive and held for the owner.

All additive and idempotent. The seed is copied here, not imported, so the migration stays as it
was written whatever the app module becomes.

Revision ID: ppr_0001_party_roles
Revises: qas_0001_quote_form_drafts
"""
from alembic import op
import sqlalchemy as sa

revision = "ppr_0001_party_roles"
down_revision = "qas_0001_quote_form_drafts"
branch_labels = None
depends_on = None

SET_KEY = "project_party_role"
SET_NAME = "Project - Party role"
ROLES = (
    ("developer", "Developer", False),
    ("architect", "Architect", False),
    ("main_contractor", "Main contractor", False),
    ("trading_house", "Trading house", True),
    ("subcontractor", "Subcontractor", True),
    ("tender_party", "Tender party", True),
    ("consultant", "Consultant", False),
    ("interior_designer", "Interior designer", False),
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE lookup_options ADD COLUMN IF NOT EXISTS allows_many BOOLEAN NOT NULL DEFAULT false"
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT gen_random_uuid(), NULL, :k, :n, NULL, TRUE
            WHERE NOT EXISTS (SELECT 1 FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :k)
            """
        ),
        {"k": SET_KEY, "n": SET_NAME},
    )
    for order, (value, label, many) in enumerate(ROLES, start=1):
        bind.execute(
            sa.text(
                """
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active, allows_many)
                SELECT gen_random_uuid(), s.id, :v, :l, :o, TRUE, :m
                  FROM lookup_sets s
                 WHERE s.tenant_id IS NULL AND s.set_key = :k
                ON CONFLICT (set_id, lower(value)) DO NOTHING
                """
            ),
            {"k": SET_KEY, "v": value, "l": label, "o": order * 10, "m": many},
        )
    for column, role in (("architect_party_id", "architect"), ("main_contractor_party_id", "main_contractor")):
        bind.execute(
            sa.text(
                f"""
                INSERT INTO projects.party_links (project_id, role, party_id)
                SELECT sp.project_id, :role, sp.{column}
                  FROM projects.sales_profile sp
                 WHERE sp.{column} IS NOT NULL
                ON CONFLICT DO NOTHING
                """
            ),
            {"role": role},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM lookup_options WHERE set_id IN "
            "(SELECT id FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :k)"
        ),
        {"k": SET_KEY},
    )
    bind.execute(sa.text("DELETE FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :k"), {"k": SET_KEY})
    bind.execute(sa.text("ALTER TABLE lookup_options DROP COLUMN IF EXISTS allows_many"))
    # The backfilled party_links stay: they are the only record of who the architect and main
    # contractor were once the app stopped writing the columns.
