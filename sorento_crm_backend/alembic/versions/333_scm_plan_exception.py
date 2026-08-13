"""SCM S5: Plan Exceptions - where the restated plan disagrees with supply already placed.

Two tables, because the batch carries a fact none of its rows can.

`scm.plan_exception_batch` holds the upload that produced the batch and, crucially, that
upload's OWN delta count. AC-D2b requires the screen to reconcile "412 lines changed" with
"6 of them disagree with a placed order", and the reduction between the two is the value of
the feature. Recounting the deltas from the exceptions would make the two figures agree by
construction and hide exactly the disagreement worth seeing, so the number is carried
through unchanged from the upload that computed it.

`scm.plan_exception` is one row per disagreement. Three of its columns are JSONB and each
is FROZEN at generation rather than recomputed on read:

  * `timeline_json` - the before and after positions side by side (AC-D4). The order book
    moves daily, so a timeline recomputed when somebody opens the row is a different
    position wearing the same date, and the reviewer would be approving against numbers the
    engine never saw.
  * `reading_json`  - lifecycle, velocity, business class and last purchase date, each with
    the FIELD it was read from (AC-D9, AC-D12). Frozen for the same reason and one more: an
    item reclassified next week must not silently re-order the actions of a decision already
    taken.
  * `actions_json`  - the proposed actions, ranked by that reading (AC-D10). The rank IS the
    engine's verdict, so it is stored, not derived at read time by whatever the ordering code
    happens to say that day.

`status` is open / approved / rejected with a CHECK, and the decision columns are the audit:
who, when, which action, and the reason. Rejecting REQUIRES a reason (AC-D6) - enforced in
the service rather than the schema, because "non-empty after trimming" is not a CHECK worth
writing in SQL, but the column exists so the reason has somewhere to live.

`company_id` is stamped for the same reason every planning artefact is: an exception is a
company's decision queue, and a plan belongs to a company (migration 332). Nullable, matching
332 - a row written with no active scope is hidden by the read predicate rather than failing
the insert outright.

Revision ID: 333_scm_plan_exception
Revises: 332_scm_company_scoped_artefacts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "333_scm_plan_exception"
down_revision = "332_scm_company_scoped_artefacts"
branch_labels = None
depends_on = None

_SORENTO = "00000000-0000-0000-0000-000000000001"

_TYPES = ("shortfall_earlier", "supply_early", "supply_surplus", "supply_wrong_location")
_STATUSES = ("open", "approved", "rejected")


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table, schema="scm")


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "plan_exception_batch"):
        op.create_table(
            "plan_exception_batch",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            # The run whose frozen plan was diffed. Nullable: a batch is produced by an
            # UPLOAD, and an upload confirmed before any plan has ever run has no run to
            # name. The exceptions are still real - a PO can be placed without a run.
            sa.Column(
                "run_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("scm.reorder_run.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("as_of", sa.Date(), nullable=False),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
            # When the order book this batch diffed was uploaded. The plan is only as
            # current as this, and the screen states it rather than implying freshness.
            sa.Column("last_upload_at", sa.DateTime(), nullable=True),
            # The upload's OWN count of changed lines, carried through unchanged (AC-D2b).
            sa.Column("delta_count", sa.Integer(), nullable=False, server_default="0"),
            # Which documents the restatement covered, so a batch can be traced back to the
            # upload without joining through the import log.
            sa.Column("source_documents", postgresql.JSONB(), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("now()")),
            schema="scm",
        )
        op.create_index(
            "ix_scm_plan_exception_batch_company_id", "plan_exception_batch",
            ["company_id"], schema="scm",
        )
        op.create_index(
            "ix_scm_plan_exception_batch_generated", "plan_exception_batch",
            ["generated_at"], schema="scm",
        )
        op.execute(
            sa.text(
                "UPDATE scm.plan_exception_batch SET company_id = :co "
                "WHERE company_id IS NULL AND EXISTS (SELECT 1 FROM companies WHERE id = :co)"
            ).bindparams(co=_SORENTO)
        )

    if not _has_table(bind, "plan_exception"):
        op.create_table(
            "plan_exception",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column(
                "batch_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("scm.plan_exception_batch.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "product_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
            ),
            # Where the placed supply is going. Nullable because supply in transit names no
            # destination until it is allocated, and that is itself an exception type.
            sa.Column(
                "warehouse_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            # The fulfilment pool the recompute ran over: netting is pooled, not per
            # warehouse, so the pool is what makes the arithmetic reproducible.
            sa.Column("pool_code", sa.String(50), nullable=True),
            sa.Column("exception_type", sa.String(40), nullable=False),
            # Always positive. The TYPE carries the direction; a signed quantity would let a
            # surplus and a shortfall be told apart two different ways, which is one too many.
            sa.Column("quantity", sa.Numeric(), nullable=False),
            sa.Column(
                "purchase_order_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("po_expected_date", sa.Date(), nullable=True),
            sa.Column("timeline_json", postgresql.JSONB(), nullable=True),
            sa.Column("reading_json", postgresql.JSONB(), nullable=True),
            sa.Column("actions_json", postgresql.JSONB(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("decided_by", postgresql.UUID(as_uuid=False), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("decided_action", sa.String(40), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            # Split only: the part that moves. The remainder stays on the original line, so
            # the two sum to `quantity` (AC-D11b).
            sa.Column("split_qty", sa.Numeric(), nullable=True),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("now()")),
            sa.CheckConstraint(
                "exception_type IN ('" + "', '".join(_TYPES) + "')",
                name="ck_scm_plan_exception_type",
            ),
            sa.CheckConstraint(
                "status IN ('" + "', '".join(_STATUSES) + "')",
                name="ck_scm_plan_exception_status",
            ),
            schema="scm",
        )
        op.create_index(
            "ix_scm_plan_exception_batch", "plan_exception", ["batch_id"], schema="scm",
        )
        # The queue query: this batch's open rows. Status leads because "what is left to
        # decide" is the question the screen opens on.
        op.create_index(
            "ix_scm_plan_exception_batch_status", "plan_exception",
            ["batch_id", "status"], schema="scm",
        )
        op.create_index(
            "ix_scm_plan_exception_company_id", "plan_exception", ["company_id"],
            schema="scm",
        )
        op.execute(
            sa.text(
                "UPDATE scm.plan_exception SET company_id = :co "
                "WHERE company_id IS NULL AND EXISTS (SELECT 1 FROM companies WHERE id = :co)"
            ).bindparams(co=_SORENTO)
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "plan_exception"):
        op.drop_table("plan_exception", schema="scm")
    if _has_table(bind, "plan_exception_batch"):
        op.drop_table("plan_exception_batch", schema="scm")
