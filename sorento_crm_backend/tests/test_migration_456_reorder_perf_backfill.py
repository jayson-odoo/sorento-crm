"""Migration `456_reorder_perf_quickwins` (S3, issue #464) - the ONE-TIME backfill of
`scm.reorder_run.{planned,decided,confirmed}_count` and (product/network-grain rows
only - see below) `scm.reorder_recommendation.pool_warehouse_{id,code}`.

Runs the migration's own SQL against `blank_session`'s scratch schema rather than
importing and executing the module directly. That is a deliberate departure from the
usual `MigrationContext`/`Operations.context` pattern
(`tests/test_migration_450_spec_rules_backfill.py`): this migration's body names
`scm.reorder_run` / `scm.reorder_recommendation` with an explicit, LITERAL schema
prefix throughout, and `blank_session`'s `schema_translate_map` does not rewrite raw
`text()` SQL - only ORM/Table-compiled statements. Running the real `upgrade()` would
silently read and write the REAL shared `scm.reorder_run` / `scm.reorder_recommendation`
tables (potentially ~400k rows) instead of the scratch copy, exactly the gotcha recorded
in `tests/test_migration_ed706a98ddc6_fulfilment_policy_settings.py`'s own docstring for
`scm.priority_policy` / migration 385.

So this file reproduces the migration's THREE backfill statements verbatim, with only the
`scm.` prefix on `reorder_run` / `reorder_recommendation` stripped - `blank_session` sets
`search_path` to resolve the bare names against its scratch `scm` copy, and
`purchase_order_lines` / `warehouses` (public, unqualified in the migration already) need
no change. Any edit to the migration's backfill SQL must be mirrored here or this file
silently stops proving what it claims to.

That reproduction is what caught a real defect in the migration as first written: its
network/product-grain pool backfill was `UPDATE ... FROM LATERAL (...) alias ON true`,
correlating the LATERAL subquery against the UPDATE's own target table (`rr`) - Postgres
does not allow that (`syntax error at or near "ON"`; dropping the `ON` instead raises
`invalid reference to FROM-clause entry for table "rr"`). Confirmed directly against the
real database: every one of the 52,168 rows with `warehouse_id IS NULL` carried a NULL
`pool_warehouse_id` - that backfill block never ran. Both the migration and this file's
copy of it now use a CTE (the LATERAL correlation happens inside an ordinary SELECT,
which Postgres does allow, then the UPDATE joins back to it by id).

The migration's LOCATION-grain pool backfill (`WHERE rr.warehouse_id = w.id`) was
dropped entirely (review finding S2) - it was a 671,125-row / ~2.5GB `UPDATE` on the
real database, and provably unnecessary: `list_recommendations`'s read path already
does `COALESCE(rr.pool_warehouse_id, w.pool_warehouse_id, w.id)`, which computes the
identical answer for a location-grain row whose `pool_warehouse_id` stays NULL, off
the same live join, forever. That equivalence is asserted directly in
`tests/scm/test_s3_reorder_perf_quickwins.py::
test_a_never_backfilled_location_row_still_reads_its_pool_via_the_live_fallback`
rather than here, since it is a READ-PATH property, not something this migration does.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import PlanRowDecision, ReorderRecommendation, ReorderRun
from tests._pg_fixture import blank_session, unique_code

# The migration's own three UPDATE statements (see
# `alembic/versions/456_reorder_perf_quickwins.py`), `scm.` stripped from
# `reorder_run` / `reorder_recommendation` only - see file docstring.
_BACKFILL_COUNTS = """
UPDATE reorder_run rr
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
      FROM reorder_recommendation r
      LEFT JOIN plan_row_decision d ON d.recommendation_id = r.id
      LEFT JOIN purchase_order_lines pol
             ON pol.source_ref = r.id::text
            AND pol.source_system IN ('scm_recommendation', 'scm_order_summary_row')
     WHERE r.rec_type IN ('buy', 'covered', 'needs_level', 'disposition')
     GROUP BY r.run_id
  ) c
 WHERE rr.id = c.run_id
"""

_BACKFILL_NETWORK_POOL = """
WITH plan_pool AS (
    SELECT rr.id AS rec_id,
           pool.pool_id::uuid AS pool_warehouse_id,
           pool.pool_code AS pool_warehouse_code
      FROM reorder_recommendation rr
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
UPDATE reorder_recommendation rr
   SET pool_warehouse_id = plan_pool.pool_warehouse_id,
       pool_warehouse_code = plan_pool.pool_warehouse_code
  FROM plan_pool
 WHERE rr.id = plan_pool.rec_id
"""


def _run_backfill(db) -> None:
    db.execute(text(_BACKFILL_COUNTS))
    db.execute(text(_BACKFILL_NETWORK_POOL))
    db.flush()


@pytest.fixture()
def db():
    with blank_session() as s:
        yield s


def _category(db) -> ProductCategory:
    row = ProductCategory(id=str(uuid.uuid4()), category_code=unique_code("CAT"),
                          category_name="ZZT category")
    db.add(row)
    db.flush()
    return row


def _uom(db) -> UnitOfMeasure:
    row = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM"), uom_name="ZZT unit")
    db.add(row)
    db.flush()
    return row


def _product(db, cat, uom) -> Product:
    row = Product(id=str(uuid.uuid4()), product_code=unique_code("P"), product_name="ZZT product",
                  category_id=cat.id, base_uom_id=uom.id, list_price=0)
    db.add(row)
    db.flush()
    return row


def _warehouse(db, *, pool_warehouse_id=None) -> Warehouse:
    row = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("W"),
                    warehouse_name="ZZT warehouse", is_active=True,
                    pool_warehouse_id=pool_warehouse_id)
    db.add(row)
    db.flush()
    return row


def _run(db, *, decision_grain="location") -> ReorderRun:
    row = ReorderRun(id=str(uuid.uuid4()), status="completed", decision_grain=decision_grain,
                     front_planning_contract_version=1)
    db.add(row)
    db.flush()
    return row


def _rec(db, run, product, *, warehouse_id=None, rec_type="buy", inputs=None) -> ReorderRecommendation:
    row = ReorderRecommendation(id=str(uuid.uuid4()), run_id=run.id, rec_type=rec_type,
                                product_id=product.id, warehouse_id=warehouse_id, inputs=inputs)
    db.add(row)
    db.flush()
    return row


def _decision(db, rec) -> PlanRowDecision:
    row = PlanRowDecision(id=str(uuid.uuid4()), recommendation_id=rec.id, kind="buy", buy_qty=10)
    db.add(row)
    db.flush()
    return row


def _draft_po_line(db, rec) -> PurchaseOrderLine:
    po = PurchaseOrder(id=str(uuid.uuid4()), po_number=unique_code("PO"), status="draft_recommendation")
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=rec.product_id,
                             warehouse_id=rec.warehouse_id, qty_ordered=10,
                             source_ref=rec.id, source_system="scm_recommendation")
    db.add(line)
    db.flush()
    return line


# ===========================================================================
# planned / decided / confirmed counts
# ===========================================================================

def test_planned_counts_distinct_products_not_recommendation_rows(db):
    """R14 - three location-grain recs on ONE product still count as ONE planned
    product, matching the read path's own by-DISTINCT-product rule."""
    cat, uom = _category(db), _uom(db)
    run = _run(db)
    product = _product(db, cat, uom)
    for _ in range(3):
        _rec(db, run, product, warehouse_id=_warehouse(db).id)

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRun).filter(ReorderRun.id == run.id).one()
    assert refreshed.planned_count == 1
    assert refreshed.decided_count == 0
    assert refreshed.confirmed_count == 0


def test_disposition_and_exception_rec_types_split(db):
    """`decided`/`confirmed`/`planned` count `buy|covered|needs_level|disposition`
    (the plan-row-decidable set at migration time); an `exception` row is excluded
    from the denominator entirely."""
    cat, uom = _category(db), _uom(db)
    run = _run(db)
    counted = _product(db, cat, uom)
    excluded = _product(db, cat, uom)
    _rec(db, run, counted, warehouse_id=_warehouse(db).id, rec_type="disposition")
    _rec(db, run, excluded, warehouse_id=_warehouse(db).id, rec_type="exception")

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRun).filter(ReorderRun.id == run.id).one()
    assert refreshed.planned_count == 1


def test_decided_count_follows_plan_row_decision(db):
    cat, uom = _category(db), _uom(db)
    run = _run(db)
    decided_product = _product(db, cat, uom)
    undecided_product = _product(db, cat, uom)
    decided_rec = _rec(db, run, decided_product, warehouse_id=_warehouse(db).id)
    _decision(db, decided_rec)
    _rec(db, run, undecided_product, warehouse_id=_warehouse(db).id)

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRun).filter(ReorderRun.id == run.id).one()
    assert refreshed.planned_count == 2
    assert refreshed.decided_count == 1


def test_confirmed_count_follows_a_draft_or_active_po_line_either_source_system(db):
    cat, uom = _category(db), _uom(db)
    run = _run(db)
    confirmed_product = _product(db, cat, uom)
    unconfirmed_product = _product(db, cat, uom)
    confirmed_rec = _rec(db, run, confirmed_product, warehouse_id=_warehouse(db).id)
    _decision(db, confirmed_rec)
    _draft_po_line(db, confirmed_rec)
    _rec(db, run, unconfirmed_product, warehouse_id=_warehouse(db).id)

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRun).filter(ReorderRun.id == run.id).one()
    assert refreshed.confirmed_count == 1


# ===========================================================================
# pool_warehouse_id / pool_warehouse_code - location grain is DELIBERATELY
# never backfilled (review finding S2) - guards against the 671,125-row UPDATE
# quietly coming back
# ===========================================================================

def test_a_location_grain_row_stays_null_the_read_path_covers_it_instead(db):
    """No backfill touches `warehouse_id IS NOT NULL` rows at all - this pins that,
    so a future edit cannot silently reintroduce the dropped 671,125-row / ~2.5GB
    `UPDATE`. `tests/scm/test_s3_reorder_perf_quickwins.py::
    test_a_never_backfilled_location_row_still_reads_its_pool_via_the_live_fallback`
    is the read-path half of this claim - the API answers correctly anyway."""
    cat, uom = _category(db), _uom(db)
    pool = _warehouse(db)
    member = _warehouse(db, pool_warehouse_id=pool.id)
    run = _run(db)
    rec = _rec(db, run, _product(db, cat, uom), warehouse_id=member.id)

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRecommendation).filter(ReorderRecommendation.id == rec.id).one()
    assert refreshed.pool_warehouse_id is None
    assert refreshed.pool_warehouse_code is None


# ===========================================================================
# pool_warehouse_id / pool_warehouse_code - product/network grain
# (`warehouse_id IS NULL`), read off `inputs.plan_basis.locations`
# ===========================================================================

def test_a_network_row_whose_locations_share_one_pool_names_it(db):
    cat, uom = _category(db), _uom(db)
    pool = _warehouse(db)
    member_a = _warehouse(db, pool_warehouse_id=pool.id)
    member_b = _warehouse(db, pool_warehouse_id=pool.id)
    run = _run(db, decision_grain="product")
    rec = _rec(
        db, run, _product(db, cat, uom), warehouse_id=None,
        inputs={"plan_basis": {"locations": [
            {"warehouse_id": member_a.id}, {"warehouse_id": member_b.id},
        ]}},
    )

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRecommendation).filter(ReorderRecommendation.id == rec.id).one()
    assert refreshed.pool_warehouse_id == pool.id
    assert refreshed.pool_warehouse_code == pool.warehouse_code


def test_a_network_row_split_across_two_pools_names_neither(db):
    """The COALESCE fallback that leaves a genuine multi-pool group `(None, None)` -
    the same "name none rather than one of several" rule the read-path LATERAL used
    to apply on every request (`reorder_run_service._group_pool_from_basis`)."""
    cat, uom = _category(db), _uom(db)
    pool_a = _warehouse(db)
    pool_b = _warehouse(db)
    member_a = _warehouse(db, pool_warehouse_id=pool_a.id)
    member_b = _warehouse(db, pool_warehouse_id=pool_b.id)
    run = _run(db, decision_grain="product")
    rec = _rec(
        db, run, _product(db, cat, uom), warehouse_id=None,
        inputs={"plan_basis": {"locations": [
            {"warehouse_id": member_a.id}, {"warehouse_id": member_b.id},
        ]}},
    )

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRecommendation).filter(ReorderRecommendation.id == rec.id).one()
    assert refreshed.pool_warehouse_id is None
    assert refreshed.pool_warehouse_code is None


def test_a_network_row_with_no_plan_basis_at_all_stays_null(db):
    """The COALESCE fallback path for a row built with no `inputs.plan_basis` -
    nothing to derive a consensus pool FROM, so it stays unset rather than erroring."""
    cat, uom = _category(db), _uom(db)
    run = _run(db, decision_grain="product")
    rec = _rec(db, run, _product(db, cat, uom), warehouse_id=None, inputs={})

    _run_backfill(db)

    db.expire_all()
    refreshed = db.query(ReorderRecommendation).filter(ReorderRecommendation.id == rec.id).one()
    assert refreshed.pool_warehouse_id is None
    assert refreshed.pool_warehouse_code is None


def test_backfill_is_idempotent(db):
    """Running it twice (the migration's own `IF NOT EXISTS` column guards make a
    second `upgrade()` a real possibility on a database migrated more than once)
    reproduces the exact same values, not a second summation. `rec` is
    location-grain (deliberately never pool-backfilled, review finding S2) so its own
    idempotence check is "stays NULL both times"; `network_rec` covers the
    network-grain CTE backfill's idempotence, the piece that still runs."""
    cat, uom = _category(db), _uom(db)
    pool = _warehouse(db)
    member = _warehouse(db, pool_warehouse_id=pool.id)
    run = _run(db)
    rec = _rec(db, run, _product(db, cat, uom), warehouse_id=member.id)
    _decision(db, rec)
    network_rec = _rec(
        db, run, _product(db, cat, uom), warehouse_id=None,
        inputs={"plan_basis": {"locations": [{"warehouse_id": member.id}]}},
    )

    _run_backfill(db)
    _run_backfill(db)

    db.expire_all()
    refreshed_run = db.query(ReorderRun).filter(ReorderRun.id == run.id).one()
    refreshed_rec = db.query(ReorderRecommendation).filter(ReorderRecommendation.id == rec.id).one()
    refreshed_network = (
        db.query(ReorderRecommendation).filter(ReorderRecommendation.id == network_rec.id).one()
    )
    assert refreshed_run.planned_count == 2
    assert refreshed_run.decided_count == 1
    assert refreshed_rec.pool_warehouse_id is None
    assert refreshed_network.pool_warehouse_id == pool.id
