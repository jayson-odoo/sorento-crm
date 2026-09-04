"""`autocount` joins the order-link claim's source vocabulary (AC-V4-3, S0).

The ESB attributes an SO/PO pairing via `from_so_numbers` on the pushed document (V4);
that write needs its own source word, the same way `crm_supply` got one in migration
458 for the supply writer's own claim. `autocount` names "a claim the ESB told Sorento
about", distinct from every existing value: not a book column (`po_history`/`po_upload`),
not a person in the Link dialog (`manual`), not the supply writer's own write-time
inference (`crm_supply`), not the link's own audit echo (`order_inquiry`).

Constraint only - no data moves; widening what is allowed cannot invalidate anything
already stored.

Revision ID: 473_scm_claim_autocount_source
Revises: 472_ingest_v2_permissions
"""
import sqlalchemy as sa
from alembic import op

revision = "473_scm_claim_autocount_source"
down_revision = "472_ingest_v2_permissions"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_scm_order_link_claim_source"
_OLD = (
    "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', 'manual', "
    "'crm_supply')"
)
_NEW = (
    "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', 'manual', "
    "'crm_supply', 'autocount')"
)


def apply(bind) -> None:
    bind.execute(sa.text(f"ALTER TABLE scm.order_link_claim DROP CONSTRAINT {_CONSTRAINT}"))
    bind.execute(
        sa.text(f"ALTER TABLE scm.order_link_claim ADD CONSTRAINT {_CONSTRAINT} CHECK ({_NEW})")
    )


def revert(bind) -> None:
    # An `autocount` row would fail the narrower check, so it is relabelled rather than
    # deleted - the attribution is real evidence and a downgrade that destroys it is
    # worse than one that stores it under the nearest older word.
    bind.execute(
        sa.text("UPDATE scm.order_link_claim SET source = 'manual' WHERE source = 'autocount'")
    )
    bind.execute(sa.text(f"ALTER TABLE scm.order_link_claim DROP CONSTRAINT {_CONSTRAINT}"))
    bind.execute(
        sa.text(f"ALTER TABLE scm.order_link_claim ADD CONSTRAINT {_CONSTRAINT} CHECK ({_OLD})")
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
