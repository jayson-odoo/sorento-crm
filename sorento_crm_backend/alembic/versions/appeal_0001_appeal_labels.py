"""COMPLAINT-APPEAL-WORDING: the status-engine graphs read "Appealed" / "Appeal".

Owner, 28 Oct 2026: every form calls a send-back after a rejection an appeal. Display only:
the stored key stays `resubmitted`. The quotation and dealer-kit edition graphs keep their
labels in rows (`statuses`, `status_transitions`, seeded by resub_0001 and the boot seeder),
so those rows are relabelled here. Data only, idempotent, no DDL.

Only the label the seed wrote is touched: a rung or edge an admin renamed keeps its name.

Plan: documentation/plans/forms/PLAN-complaint-appeal-wording-28oct.md.

Revision ID: appeal_0001_appeal_labels
Revises: dimany_0001_unit_aliases
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "appeal_0001_appeal_labels"
down_revision = "dimany_0001_unit_aliases"
branch_labels = None
depends_on = None

_ENTITIES = ("quotation", "dealer_kit_edition")


def relabel(bind, *, status_from: str, status_to: str, edge_from: str, edge_to: str) -> None:
    bind.execute(
        sa.text(
            "UPDATE statuses SET label = :to, updated_at = now() "
            "WHERE entity_type IN :ets AND key = 'resubmitted' AND label = :from"
        ).bindparams(sa.bindparam("ets", expanding=True)),
        {"to": status_to, "from": status_from, "ets": list(_ENTITIES)},
    )
    bind.execute(
        sa.text(
            "UPDATE status_transitions SET label = :to, updated_at = now() "
            "WHERE entity_type IN :ets AND label = :from AND to_status_id IN "
            "(SELECT id FROM statuses WHERE key = 'resubmitted')"
        ).bindparams(sa.bindparam("ets", expanding=True)),
        {"to": edge_to, "from": edge_from, "ets": list(_ENTITIES)},
    )


def upgrade() -> None:
    relabel(
        op.get_bind(),
        status_from="Resubmitted",
        status_to="Appealed",
        edge_from="Resubmit for approval",
        edge_to="Appeal",
    )


def downgrade() -> None:
    relabel(
        op.get_bind(),
        status_from="Appealed",
        status_to="Resubmitted",
        edge_from="Appeal",
        edge_to="Resubmit for approval",
    )
