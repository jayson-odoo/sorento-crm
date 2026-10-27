"""RESUBMITTED-STATUS: a form submitted again after a rejection carries status `resubmitted`.

Additive only, idempotent, and safe on the shared dev DB that converges through `create_all`.

1. `new_product_applications.status` is the one plain status column with a CHECK, so the
   constraint is widened to accept `resubmitted`. The other plain-column forms (complaints,
   purchase requests / sponsorship forms, stock inquiries, project registrations) keep free-text
   status columns and need no DDL.
2. The two status-graph forms (quotation approval, dealer-kit edition) get a `resubmitted` rung
   in their DEFAULT graph, copied from that graph's own `pending_approval` row (category, colour,
   sort order, system flag) because it is decided exactly like pending, plus three edges:
   draft -> resubmitted, resubmitted -> approved, resubmitted -> rejected. Skip-if-present per
   row and per edge, like migration 318, and only where the graph exists at all: a database that
   has never seeded a graph gets it from the boot seeder instead.
3. The Edition's one-open-per-page partial unique index is recreated with `resubmitted` among the
   open keys, so a resubmitted Edition still occupies its page's one open slot.

Downgrade moves every record off `resubmitted` back onto the stage it stood in for (submitted,
pending_project_sales, pending, pending_approval) first, so the old code's gates still accept it
and the narrower constraint and index can return.

Plan: documentation/plans/forms/PLAN-resubmitted-status-27oct.md.

Revision ID: resub_0001_resubmitted_status
Revises: sales_unified_0002
"""
import uuid

import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "resub_0001_resubmitted_status"
down_revision = "sales_unified_0002"
branch_labels = None
depends_on = None

RESUBMITTED = "resubmitted"

_NPA_STATUSES_OLD = "'draft','submitted','approved','rejected','completed','cancelled'"
_NPA_STATUSES_NEW = "'draft','submitted','resubmitted','approved','rejected','completed','cancelled'"

# entity_type -> (from_key, to_key, label, sort) for the three edges the rung needs.
_GRAPH_EDGES = {
    "quotation": (
        ("draft", RESUBMITTED, "Resubmit for approval", 1),
        (RESUBMITTED, "approved", "Approve", 0),
        (RESUBMITTED, "rejected", "Reject", 1),
    ),
    "dealer_kit_edition": (
        ("draft", RESUBMITTED, "Resubmit for approval", 15),
        (RESUBMITTED, "approved", "Approve", 20),
        (RESUBMITTED, "rejected", "Reject", 30),
    ),
}

_EDITION_INDEX = "uq_dealer_kit_edition_one_open_per_page"
_EDITION_OPEN_OLD = "'draft', 'pending_approval', 'approved', 'rejected'"
_EDITION_OPEN_NEW = "'draft', 'pending_approval', 'resubmitted', 'approved', 'rejected'"


def _status_id(bind, entity: str, key: str):
    return bind.execute(
        sa.text(
            "SELECT id FROM statuses WHERE entity_type = :et AND key = :key AND scope_id IS NULL"
        ),
        {"et": entity, "key": key},
    ).scalar()


def seed_resubmitted_rungs(bind) -> None:
    """Add the `resubmitted` rung and its edges to each existing default graph."""
    for entity, edges in _GRAPH_EDGES.items():
        pending = bind.execute(
            sa.text(
                "SELECT category, color_hex, sort_order, is_system FROM statuses "
                "WHERE entity_type = :et AND key = 'pending_approval' AND scope_id IS NULL"
            ),
            {"et": entity},
        ).first()
        if pending is None:
            continue  # no graph yet: the boot seeder (or 318) builds it whole
        if _status_id(bind, entity, RESUBMITTED) is None:
            bind.execute(
                sa.text(
                    "INSERT INTO statuses "
                    "(id, entity_type, key, label, category, color_hex, sort_order, "
                    " is_initial, is_terminal, is_active, is_archived, is_default, is_system, "
                    " created_at, updated_at) "
                    "VALUES (:id, :et, :key, 'Resubmitted', :cat, :colour, :sort, "
                    " false, false, true, false, false, :system, now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "et": entity,
                    "key": RESUBMITTED,
                    "cat": pending.category,
                    "colour": pending.color_hex,
                    "sort": pending.sort_order,
                    "system": bool(pending.is_system),
                },
            )
        for from_key, to_key, label, sort in edges:
            from_id = _status_id(bind, entity, from_key)
            to_id = _status_id(bind, entity, to_key)
            if not from_id or not to_id:
                continue  # an admin removed that rung; do not resurrect it
            already = bind.execute(
                sa.text(
                    "SELECT 1 FROM status_transitions WHERE entity_type = :et "
                    "AND from_status_id = :f AND to_status_id = :t AND scope_id IS NULL"
                ),
                {"et": entity, "f": from_id, "t": to_id},
            ).scalar()
            if already:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO status_transitions "
                    "(id, entity_type, from_status_id, to_status_id, label, sort_order, "
                    " trigger_mode, created_at, updated_at) "
                    "VALUES (:id, :et, :f, :t, :label, :sort, 'manual', now(), now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "et": entity,
                    "f": from_id,
                    "t": to_id,
                    "label": label,
                    "sort": sort,
                },
            )


def _recreate_edition_index(open_keys: str) -> None:
    op.execute(f"DROP INDEX IF EXISTS dealer_kit.{_EDITION_INDEX}")
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_EDITION_INDEX} "
        f"ON dealer_kit.edition (page_id) WHERE status_key IN ({open_keys})"
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE new_product_applications "
        "DROP CONSTRAINT IF EXISTS ck_new_product_applications_status"
    )
    op.execute(
        "ALTER TABLE new_product_applications ADD CONSTRAINT ck_new_product_applications_status "
        f"CHECK (status IN ({_NPA_STATUSES_NEW}))"
    )
    seed_resubmitted_rungs(op.get_bind())
    _recreate_edition_index(_EDITION_OPEN_NEW)


# The free-text status columns, and the stage `resubmitted` stood in for on each.
_FREE_TEXT_STAGES = (
    ("complaints", "status", "submitted"),
    ("purchase_requests", "status", "submitted"),
    ("new_product_applications", "status", "submitted"),
    ("stock_inquiries", "status", "pending_project_sales"),
    ("projects.projects", "approval_state", "pending"),
)


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, stage in _FREE_TEXT_STAGES:
        op.execute(f"UPDATE {table} SET {column} = '{stage}' WHERE {column} = 'resubmitted'")
    op.execute(
        "ALTER TABLE new_product_applications "
        "DROP CONSTRAINT IF EXISTS ck_new_product_applications_status"
    )
    op.execute(
        "ALTER TABLE new_product_applications ADD CONSTRAINT ck_new_product_applications_status "
        f"CHECK (status IN ({_NPA_STATUSES_OLD}))"
    )
    for entity in _GRAPH_EDGES:
        rung = _status_id(bind, entity, RESUBMITTED)
        pending = _status_id(bind, entity, "pending_approval")
        if rung is None:
            continue
        if pending is not None:
            if entity == "quotation":
                move_back = (
                    "UPDATE projects.quotation_documents SET approval_status_id = :p "
                    "WHERE approval_status_id = :r"
                )
            else:
                move_back = (
                    "UPDATE dealer_kit.edition SET status_id = :p, "
                    "status_key = 'pending_approval' WHERE status_id = :r"
                )
            bind.execute(sa.text(move_back), {"p": pending, "r": rung})
        bind.execute(
            sa.text(
                "DELETE FROM status_transitions WHERE from_status_id = :r OR to_status_id = :r"
            ),
            {"r": rung},
        )
        bind.execute(sa.text("DELETE FROM statuses WHERE id = :r"), {"r": rung})
    _recreate_edition_index(_EDITION_OPEN_OLD)
