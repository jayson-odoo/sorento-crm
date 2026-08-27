"""S7: supplier inventory snapshot, container sizes, and the Loading Plan.

Revision ID: 336_scm_supplier_inventory_loading_plan
Revises: 335_scm_order_link_claim_per_company
Create Date: 2026-08-05

Three tables and one seed:

* `scm.supplier_inventory` - what a supplier is holding, packed versus unfinished, with a
  per-unit volume. A snapshot per supplier: the next file replaces it.
* `scm.container_size` - the volume of a container, per tenant (AC-E3). Seeded with the
  three the client actually ships in; a client who loads something else edits the row
  instead of needing code.
* `scm.loading_plan` + `scm.loading_plan_line` - the fill decision and every candidate's
  outcome, including the deferred ones, because "why is this not on the container" is the
  question the screen exists to answer.

The alias rows these importers read (`supplier_inventory`, `packing_list`, both in the
supplier's own Chinese) were already seeded by migration 311, so nothing is re-seeded here.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "336_scm_supplier_inventory_loading_plan"
down_revision = "335_scm_order_link_claim_per_company"
branch_labels = None
depends_on = None


#: (code, label, cbm). Internal loadable volume, not the nominal external size: a 40HQ is
#: sold as 76 cbm and planning to the brochure figure is how a container arrives one pallet
#: short of the manifest.
#:
#: The 40HQ figure was 68 here until 26 Aug, when the captain ruled it to 65 - what Ms Tee
#: actually loads to (Q3, `PLAN-scm-fulfilment-feedback.md`). Changed AT THE SEED as well as
#: in the data migration that corrects already-seeded databases (428), because a CI database
#: is built with `create_all` + these seed helpers and never runs a migration body: leaving
#: 68 here would give a fresh install the old capacity for ever.
_CONTAINER_SIZES = (
    ("20GP", "20ft standard", 28.0),
    ("40GP", "40ft standard", 58.0),
    ("40HQ", "40ft high cube", 65.0),
)


def upgrade() -> None:
    op.create_table(
        "supplier_inventory",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "supplier_id",
            UUID(as_uuid=False),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_code", sa.String(100), nullable=False),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("qty_packed", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("qty_unfinished", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("cbm_per_unit", sa.Numeric(), nullable=True),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("spec", sa.String(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("uploaded_by", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="scm",
    )
    op.create_index(
        "ix_scm_supplier_inventory_supplier", "supplier_inventory", ["supplier_id"], schema="scm"
    )
    op.create_index(
        "ix_scm_supplier_inventory_product", "supplier_inventory", ["product_id"], schema="scm"
    )
    # One row per item per supplier per company. Company is coalesced for the same reason as
    # the order-link claim: the column is nullable on legacy rows and Postgres treats NULLs as
    # distinct, so without it a re-upload inserts a second row and the packed quantity doubles.
    op.create_index(
        "uq_scm_supplier_inventory_identity",
        "supplier_inventory",
        [
            sa.text("coalesce(company_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "supplier_id",
            "item_code",
        ],
        unique=True,
        schema="scm",
    )

    op.create_table(
        "container_size",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=False), nullable=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("cbm", sa.Numeric(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("cbm > 0", name="ck_scm_container_size_cbm"),
        schema="scm",
    )
    op.create_index(
        "uq_scm_container_size_code",
        "container_size",
        [
            sa.text("coalesce(company_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("upper(code)"),
        ],
        unique=True,
        schema="scm",
    )

    op.create_table(
        "loading_plan",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "supplier_id",
            UUID(as_uuid=False),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("container_type", sa.String(30), nullable=True),
        sa.Column("container_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("container_cbm", sa.Numeric(), nullable=False),
        sa.Column("capacity_cbm", sa.Numeric(), nullable=False),
        sa.Column(
            "policy_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.priority_policy.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("inventory_as_of", sa.Date(), nullable=True),
        sa.Column("planned_cbm", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deferred_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unmeasured_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("container_count > 0", name="ck_scm_loading_plan_containers"),
        sa.CheckConstraint("container_cbm > 0", name="ck_scm_loading_plan_container_cbm"),
        schema="scm",
    )
    op.create_index("ix_scm_loading_plan_supplier", "loading_plan", ["supplier_id"], schema="scm")

    op.create_table(
        "loading_plan_line",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "plan_id",
            UUID(as_uuid=False),
            sa.ForeignKey("scm.loading_plan.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "po_line_id",
            UUID(as_uuid=False),
            sa.ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("po_number", sa.String(100), nullable=True),
        sa.Column("item_code", sa.String(100), nullable=True),
        sa.Column("qty_outstanding", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("qty_packed_available", sa.Numeric(), nullable=True),
        sa.Column("qty_planned", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("cbm_per_unit", sa.Numeric(), nullable=True),
        sa.Column("cbm_planned", sa.Numeric(), nullable=True),
        sa.Column("volume_basis", sa.String(20), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("rank_score", sa.Numeric(), nullable=True),
        sa.Column("factors_json", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'deferred'")
        ),
        sa.Column("deferral_reason", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('allocated', 'partial', 'deferred', 'unmeasured')",
            name="ck_scm_loading_plan_line_status",
        ),
        schema="scm",
    )
    op.create_index(
        "ix_scm_loading_plan_line_plan", "loading_plan_line", ["plan_id"], schema="scm"
    )
    op.create_index(
        "uq_scm_loading_plan_line_identity",
        "loading_plan_line",
        ["plan_id", "po_line_id"],
        unique=True,
        schema="scm",
    )

    seed_container_sizes(op.get_bind())


def seed_container_sizes(bind) -> int:
    """Insert the three container sizes when they are absent. Idempotent, importable.

    Importable because a fresh CI database is built with `create_all`, which runs no
    migration body - so a test that needs the seed calls this instead of asserting that
    somebody else ran it.
    """
    inserted = 0
    for code, label, cbm in _CONTAINER_SIZES:
        res = bind.execute(
            sa.text(
                """
                INSERT INTO scm.container_size (id, code, label, cbm, is_default)
                SELECT gen_random_uuid(), :c, :l, :v, :d
                WHERE NOT EXISTS (
                    SELECT 1 FROM scm.container_size WHERE upper(code) = upper(:c)
                )
                """
            ),
            {"c": code, "l": label, "v": cbm, "d": code == "40HQ"},
        )
        inserted += res.rowcount or 0
    return inserted


def downgrade() -> None:
    op.drop_table("loading_plan_line", schema="scm")
    op.drop_table("loading_plan", schema="scm")
    op.drop_table("container_size", schema="scm")
    op.drop_table("supplier_inventory", schema="scm")
