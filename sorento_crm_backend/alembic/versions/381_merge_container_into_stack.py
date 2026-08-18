"""Rejoin the multi-supplier container lane with the integration branch's head.

No DDL. A merge revision only joins lineages so `alembic upgrade head` (and the
`alembic stamp head` that `scripts/bootstrap_env.py` runs on a fresh CI database)
has ONE target.

**Why there are two.** The container lane cut its own join against main's Project
Sales merge, while the integration branch had stacked six SCM lanes above the same
revision:

    375_merge_shipment_supplier  (container: joins 374_merge_proj_media_flyer and
                                  374_shipment_line_supplier)
    380_merge_kailu_into_stack   (integration: the head after Stage 0/1A, 1B, 1C,
                                  Stage 2, proforma and the Kailu aliases)

They are siblings, so merging the container branch in leaves two heads. Two heads is
not a warning, it is a broken deploy: `alembic upgrade head` refuses to guess and
`bootstrap_env` aborts its stamp with "Multiple heads are present" before a single
test runs. This revision joins forward from both.

No `depends_on` is needed, and that was checked rather than assumed.
`374_shipment_line_supplier` is the only revision in this whole stack that touches
`inbound_shipment_lines` (it adds `supplier_id`, `cbm` and `remarks`, and swaps the
`(shipment, product)` unique index for `(shipment, product, supplier)` NULLS NOT
DISTINCT). The proforma lane creates its own tables, the Kailu and proforma lanes
seed `import_field_alias`, and the front-planning lanes work in `projects` and `scm`.
Nothing overlaps, so the order between the two branches genuinely does not matter.

Neither parent is renumbered or deleted; both are landed on their branches and any
database stamped with either must still be able to upgrade. Join forward, never
renumber a landed revision.

The id is 30 characters. A database provisioned by a plain `alembic stamp` gets
`alembic_version.version_num varchar(32)`, so any head id must stay at or under 32
(see 322's docstring and `tests/test_alembic_revision_ids.py`).

Revision ID: 381_merge_container_into_stack
Revises: 380_merge_kailu_into_stack, 375_merge_shipment_supplier
Create Date: 2026-08-18
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "381_merge_container_into_stack"
down_revision = (
    "380_merge_kailu_into_stack",
    "375_merge_shipment_supplier",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
