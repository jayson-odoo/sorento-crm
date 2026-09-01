"""SCM S3 perf quick wins (PLAN-scm-reorder-oi-feedback-1sep.md / issue #464).

Three additive pieces, bundled because they land in the same PR and none depends on
another:

1. **AC-3.1** - an index on ``purchase_order_lines (source_ref, source_system)``. Every
   decision-list / plans-list read resolves a recommendation's draft/active PO line by
   this pair (``decision_service._po_for_rec``, ``_product_counts``), and with no index
   it was a sequential scan of the whole table per lookup - measured on the prod-copy DB
   at ~73k rows filtered, ~6ms each, N+1'd across a run's decided rows.
2. **AC-3.3** - ``planned_count`` / ``decided_count`` / ``confirmed_count`` on
   ``scm.reorder_run``, backfilled here and kept current by
   ``decision_service._refresh_run_counts`` from here on. The plans list and its Decided
   sort used to answer "how many products (R14) are decided/confirmed" with a LEFT JOIN
   against the whole ``purchase_order_lines`` table on every page load; this is that
   answer, stored once per write instead of recomputed on every read.
3. **AC-3.4** - ``pool_warehouse_id`` / ``pool_warehouse_code`` on
   ``scm.reorder_recommendation``, set at generation time from here on
   (``reorder_run_service._plan_basis``). Read path (``list_recommendations``) used a
   ``LEFT JOIN LATERAL`` unnesting ``inputs.plan_basis.locations`` per row to name the
   pool a product/network-grain row's members share - and that LATERAL ran for the
   MAJORITY of rows (every product-grain buy/covered/needs_level row names no single
   warehouse), not an edge case. Backfilled here ONLY for that product/network-grain
   set (52,168 rows on the real database) - a location-grain row is deliberately left
   NULL, because the read path's own ``COALESCE`` fallback already computes the exact
   answer a backfill would have written, forever (see that ``UPDATE``'s own comment
   below for why a 671,125-row / ~2.5GB pass would have bought nothing).

Revision ID: 456_reorder_perf_quickwins
Revises: 453_shared_brand_attach

Renumbered TWICE on the night of 1-2 Sep 2026: three lanes minted a 454 on 1 Sep, then
S4 (PR #489) independently minted the 455 this migration had first been renumbered to.
Global batch chain, captain's final call:
    454_order_inquiry_born_ack   (S1, PR #471)
    455_saved_views_and_perms    (S4, PR #489)
    456_reorder_perf_quickwins   (S3, this branch, PR #491)
    457                          (S5, PR #493)
Merge order: #471 -> #488 -> #489 -> #491 -> #490 -> #493.

``down_revision`` stays pinned to ``453_shared_brand_attach`` for now, deliberately NOT
``455_saved_views_and_perms`` - that revision id exists only on the S4 branch (PR #489),
not on this one, and an alembic graph with a ``down_revision`` pointing at a revision id
absent from the loaded version files fails to load AT ALL (breaks every `alembic` command,
including CI's `alembic upgrade head` for this whole PR). ``down_revision`` moves to
``455_saved_views_and_perms`` in a one-line follow-up commit immediately before #491 merges,
once #489 has landed on main and that revision id is real here too.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "456_reorder_perf_quickwins"
down_revision = "453_shared_brand_attach"
branch_labels = None
depends_on = None


def _columns(table: str, schema: str = "public") -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = :s"
            ),
            {"t": table, "s": schema},
        )
    }


def upgrade() -> None:
    # --- AC-3.1: purchase_order_lines(source_ref, source_system) -----------
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_purchase_order_lines_source_ref_system "
        "ON purchase_order_lines (source_ref, source_system)"
    )

    # --- AC-3.3: scm.reorder_run denormalised counts ------------------------
    run_columns = _columns("reorder_run", "scm")
    if "planned_count" not in run_columns:
        op.add_column(
            "reorder_run",
            sa.Column("planned_count", sa.Integer(), nullable=False, server_default="0"),
            schema="scm",
        )
    if "decided_count" not in run_columns:
        op.add_column(
            "reorder_run",
            sa.Column("decided_count", sa.Integer(), nullable=False, server_default="0"),
            schema="scm",
        )
    if "confirmed_count" not in run_columns:
        op.add_column(
            "reorder_run",
            sa.Column("confirmed_count", sa.Integer(), nullable=False, server_default="0"),
            schema="scm",
        )
    # Backfill every existing run once, with the exact query the read path used to run
    # per page (`reorder_runs._product_counts`) - by DISTINCT product (R14), never by
    # recommendation.
    op.execute(
        """
        UPDATE scm.reorder_run rr
           SET planned_count = c.planned,
               decided_count = c.decided,
               confirmed_count = c.confirmed
          FROM (
            SELECT r.run_id,
                   count(DISTINCT r.product_id) AS planned,
                   count(DISTINCT r.product_id)
                     FILTER (WHERE d.id IS NOT NULL) AS decided,
                   count(DISTINCT r.product_id)
                     FILTER (WHERE pol.id IS NOT NULL) AS confirmed
              FROM scm.reorder_recommendation r
              LEFT JOIN scm.plan_row_decision d ON d.recommendation_id = r.id
              LEFT JOIN purchase_order_lines pol
                     ON pol.source_ref = r.id::text
                    AND pol.source_system IN ('scm_recommendation', 'scm_order_summary_row')
             WHERE r.rec_type IN ('buy', 'covered', 'needs_level', 'disposition')
             GROUP BY r.run_id
          ) c
         WHERE rr.id = c.run_id
        """
    )

    # --- AC-3.4: scm.reorder_recommendation precomputed pool ----------------
    rec_columns = _columns("reorder_recommendation", "scm")
    if "pool_warehouse_id" not in rec_columns:
        op.add_column(
            "reorder_recommendation",
            sa.Column(
                "pool_warehouse_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            schema="scm",
        )
    if "pool_warehouse_code" not in rec_columns:
        op.add_column(
            "reorder_recommendation",
            sa.Column("pool_warehouse_code", sa.String(length=50), nullable=True),
            schema="scm",
        )
    # NO backfill for location-grain rows (review finding S2, dropped deliberately -
    # the earlier draft of this migration ran one, and it was a ~2.5GB / 671,125-row
    # UPDATE on the real database). It is provably unnecessary: `list_recommendations`'
    # read path already does `COALESCE(rr.pool_warehouse_id, w.pool_warehouse_id, w.id)`
    # - for a location-grain row with `rr.pool_warehouse_id IS NULL` (every row this
    # backfill would have touched), that COALESCE computes the EXACT SAME value the
    # backfill's own `COALESCE(w.pool_warehouse_id, w.id)` would have written, off the
    # SAME live join, forever - a stored NULL and a live-computed answer are
    # indistinguishable to every reader. Verified against the dev DB (reviewer). Every
    # NEW row gets the column set directly at generation time
    # (`reorder_run_service._build_rec`), so this is a permanent freeze-vs-live
    # semantics feature (R15: a re-pooled warehouse must not retroactively change a
    # FROZEN recommendation's pool), not a temporary bootstrap step to skip and revisit
    # - see the identical COALESCE's own comment in `reorder_runs.py`. A one-time
    # migration touching the whole table is exactly the deploy-timeout shape migration
    # 420 got burned by (PR #353's ~15-minute delete on an unindexed FK referrer) -
    # not worth paying for an answer the read path already gives for free.
    #
    # Backfill product/network-grain rows (`warehouse_id IS NULL`) with the SAME rule the
    # read-path LATERAL used to apply on every request: name the pool only when every
    # member location the row was sized over shares one.
    #
    # Written as a CTE rather than a bare `UPDATE ... FROM LATERAL (...) alias ON true`:
    # Postgres does not allow a LATERAL subquery in an UPDATE's FROM clause to reference
    # the UPDATE's own target table (`rr`) - that correlation is only legal inside an
    # ordinary SELECT, where the target is just another FROM item. The original form
    # raised `syntax error at or near "ON"` (dropping the `ON true` instead raises
    # `invalid reference to FROM-clause entry for table "rr"`) - a genuine defect this
    # migration shipped with and never actually ran: verified against the real database,
    # every one of its 52,168 `warehouse_id IS NULL` rows carried a NULL
    # `pool_warehouse_id` (tests/test_migration_456_reorder_perf_backfill.py). The CTE
    # does the LATERAL correlation inside a plain SELECT, then the UPDATE joins back to
    # it by id - the row-selection rule is unchanged (HAVING drops a row with zero or
    # more-than-one member pool, so the outer UPDATE simply never touches it and its
    # columns stay NULL, matching "name none rather than one of several").
    op.execute(
        """
        WITH plan_pool AS (
            SELECT rr.id AS rec_id,
                   pool.pool_id::uuid AS pool_warehouse_id,
                   pool.pool_code AS pool_warehouse_code
              FROM scm.reorder_recommendation rr
              JOIN LATERAL (
                SELECT MIN(COALESCE(lw.pool_warehouse_id, lw.id)::text) AS pool_id,
                       MIN(COALESCE(lpw.warehouse_code, lw.warehouse_code)) AS pool_code
                  FROM jsonb_array_elements(
                           COALESCE(rr.inputs -> 'plan_basis' -> 'locations', '[]'::jsonb)) loc
                  JOIN warehouses lw ON lw.id = CAST(loc ->> 'warehouse_id' AS uuid)
                  LEFT JOIN warehouses lpw ON lpw.id = lw.pool_warehouse_id
                 HAVING COUNT(DISTINCT COALESCE(lw.pool_warehouse_id, lw.id)) = 1
              ) pool ON true
             WHERE rr.warehouse_id IS NULL
        )
        UPDATE scm.reorder_recommendation rr
           SET pool_warehouse_id = plan_pool.pool_warehouse_id,
               pool_warehouse_code = plan_pool.pool_warehouse_code
          FROM plan_pool
         WHERE rr.id = plan_pool.rec_id
        """
    )


def downgrade() -> None:
    rec_columns = _columns("reorder_recommendation", "scm")
    if "pool_warehouse_code" in rec_columns:
        op.drop_column("reorder_recommendation", "pool_warehouse_code", schema="scm")
    if "pool_warehouse_id" in rec_columns:
        op.drop_column("reorder_recommendation", "pool_warehouse_id", schema="scm")

    run_columns = _columns("reorder_run", "scm")
    if "confirmed_count" in run_columns:
        op.drop_column("reorder_run", "confirmed_count", schema="scm")
    if "decided_count" in run_columns:
        op.drop_column("reorder_run", "decided_count", schema="scm")
    if "planned_count" in run_columns:
        op.drop_column("reorder_run", "planned_count", schema="scm")

    op.execute("DROP INDEX IF EXISTS ix_purchase_order_lines_source_ref_system")
