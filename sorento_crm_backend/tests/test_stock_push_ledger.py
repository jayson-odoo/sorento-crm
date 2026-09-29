"""Every AutoCount `stock_balances` push that CHANGES a quantity writes one
Stock Ledger row (#1257, fix round 2).

Owner, 26 Sep: "i don't see any log from ledger side also". The Stock Ledger
screen showed only BULK_IMPORT rows because the 5-minute push wrote nothing
there. Pinned here:

* a changed quantity writes one `AUTOCOUNT_PUSH` row: previous, new, change,
  `created_by` = the integration's act-as user, `reference_type =
  "autocount_push"`, `reference_id` = the record's `source_ref`;
* a new pair with stock writes one row from 0, a new pair at 0 writes none
  (the BULK_IMPORT rule for a new stock record);
* an UNCHANGED value writes nothing, so a push every 5 minutes is not noise;
* a deletion zeroing writes one row down to 0, an already-zero pair none;
* a dry run writes nothing;
* the insert-race path (another writer's row landed after the preload) still
  writes its one row, and a refused record writes none;
* the Stock Ledger listing filters on the new type and names the actor.

Postgres only, blank schema, every row seeded here.
"""
from __future__ import annotations

from sqlalchemy import text

from app.models.inventory import StockLedger
from app.services.inventory_service import StockService
from app.services.stock_balance_ingest_service import (
    AUTOCOUNT_PUSH,
    StockBalanceIngestService,
)

from tests.test_ingest_stock_balances import (  # noqa: F401 - `env` is a fixture
    DELETE_SB,
    INGEST_SB,
    _USER_ID,
    _ref,
    _sb_record,
    env,
)


def _ledger_rows(db, product_id, warehouse_id):
    db.expire_all()
    return (
        db.query(StockLedger)
        .filter(
            StockLedger.product_id == str(product_id),
            StockLedger.warehouse_id == str(warehouse_id),
        )
        .order_by(StockLedger.created_at.asc())
        .all()
    )


def _push(env, qty, *, ref=None, dry_run=False):
    record = _sb_record(
        item_code=env.product.product_code,
        location_code=env.wh_active.warehouse_code,
        qty=qty,
        ref=ref,
    )
    res = env.post(INGEST_SB, [record], dry_run=dry_run)
    assert res.status_code == 200, res.text
    return record, res.json()["records"][0]


def test_changed_quantity_writes_one_autocount_push_row(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=5)

    record, entry = _push(env, 9)

    assert entry["outcome"] == "updated", entry
    rows = _ledger_rows(env.db, env.product.id, env.wh_active.id)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row.transaction_type == AUTOCOUNT_PUSH == "AUTOCOUNT_PUSH"
    assert (row.previous_quantity, row.new_quantity, row.quantity_change) == (5, 9, 4)
    assert row.created_by == _USER_ID
    assert row.reference_type == "autocount_push"
    assert row.reference_id == record["source_ref"]
    assert str(row.company_id) == env.company_a


def test_unchanged_quantity_writes_no_row(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=5)

    _, entry = _push(env, 5)
    _, entry_again = _push(env, 5)

    assert entry["outcome"] == entry_again["outcome"] == "updated"
    assert _ledger_rows(env.db, env.product.id, env.wh_active.id) == []


def test_a_decrease_records_a_negative_change(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=12)

    _push(env, 3)

    (row,) = _ledger_rows(env.db, env.product.id, env.wh_active.id)
    assert (row.previous_quantity, row.new_quantity, row.quantity_change) == (12, 3, -9)


def test_new_pair_with_stock_writes_one_row_from_zero(env):
    record, entry = _push(env, 25)

    assert entry["outcome"] == "created", entry
    (row,) = _ledger_rows(env.db, env.product.id, env.wh_active.id)
    assert row.transaction_type == AUTOCOUNT_PUSH
    assert (row.previous_quantity, row.new_quantity, row.quantity_change) == (0, 25, 25)
    assert row.reference_id == record["source_ref"]
    assert row.created_by == _USER_ID


def test_new_pair_at_zero_writes_no_row(env):
    _, entry = _push(env, 0)

    assert entry["outcome"] == "created", entry
    assert _ledger_rows(env.db, env.product.id, env.wh_active.id) == []


def test_dry_run_writes_no_row(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=5)

    _push(env, 9, dry_run=True)

    assert _ledger_rows(env.db, env.product.id, env.wh_active.id) == []


def test_deletion_zeroing_writes_one_row_down_to_zero(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=7)
    ref = _ref("DEL")

    res = env.delete(
        [ref],
        {ref: {"item_code": env.product.product_code, "location_code": env.wh_active.warehouse_code}},
    )

    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "deleted"
    (row,) = _ledger_rows(env.db, env.product.id, env.wh_active.id)
    assert row.transaction_type == AUTOCOUNT_PUSH
    assert (row.previous_quantity, row.new_quantity, row.quantity_change) == (7, 0, -7)
    assert row.reference_id == ref
    assert row.created_by == _USER_ID


def test_deletion_of_an_already_zero_pair_writes_no_row(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=0)
    ref = _ref("DEL0")

    res = env.delete(
        [ref],
        {ref: {"item_code": env.product.product_code, "location_code": env.wh_active.warehouse_code}},
    )

    assert res.json()["records"][0]["outcome"] == "deleted"
    assert _ledger_rows(env.db, env.product.id, env.wh_active.id) == []


def test_insert_race_path_writes_one_row_against_the_winners_value(env, monkeypatch):
    """Another writer's row for the pair lands after this batch's preload: the
    create hits the unique index, the loser re-reads and updates. The ledger
    row carries the winner's value as `previous`."""
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=4)
    service = StockBalanceIngestService(env.db, company_id=env.company_a, actor_user_id=_USER_ID)
    real_preload = service._build_preload

    def _preload_that_misses_the_row(*args, **kwargs):
        real_preload(*args, **kwargs)
        service._stock_by_pair = {}

    monkeypatch.setattr(service, "_build_preload", _preload_that_misses_the_row)
    ref = _ref("RACE")
    result = service.ingest(
        "stock_balances",
        [
            {
                "source_ref": ref,
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
                "qty": 10,
            }
        ],
    )
    env.db.commit()

    assert result.records[0].outcome.value == "updated", result.records[0]
    (row,) = _ledger_rows(env.db, env.product.id, env.wh_active.id)
    assert (row.previous_quantity, row.new_quantity, row.quantity_change) == (4, 10, 6)
    assert row.reference_id == ref


def test_a_refused_record_writes_no_row(env, monkeypatch):
    """A record whose savepoint rolls back leaves no ledger row behind."""
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=5)
    service = StockBalanceIngestService(env.db, company_id=env.company_a, actor_user_id=_USER_ID)
    real_flush = env.db.flush
    calls = {"n": 0}

    def _flush_then_fail(*args, **kwargs):
        # Fails only the flush that carries this record's ledger row, after it
        # reached the DB, so the savepoint rollback is what must remove it.
        carries_ledger = any(isinstance(obj, StockLedger) for obj in env.db.new)
        real_flush(*args, **kwargs)
        if carries_ledger:
            calls["n"] += 1
            raise RuntimeError("boom after the ledger row was added")

    monkeypatch.setattr(env.db, "flush", _flush_then_fail)
    result = service.ingest(
        "stock_balances",
        [
            {
                "source_ref": _ref("BOOM"),
                "item_code": env.product.product_code,
                "location_code": env.wh_active.warehouse_code,
                "qty": 9,
            }
        ],
    )
    monkeypatch.setattr(env.db, "flush", real_flush)
    env.db.commit()

    assert calls["n"] == 1
    assert result.records[0].outcome.value == "failed"
    assert _ledger_rows(env.db, env.product.id, env.wh_active.id) == []
    qty = env.db.execute(
        text("SELECT quantity_on_hand FROM stock WHERE product_id = :p AND warehouse_id = :w"),
        {"p": str(env.product.id), "w": str(env.wh_active.id)},
    ).scalar()
    assert qty == 5


def test_stock_ledger_listing_filters_on_the_push_type_and_names_the_actor(env):
    env.make_stock(product_id=env.product.id, warehouse_id=env.wh_active.id, quantity_on_hand=5)
    _push(env, 8)

    listed = StockService(env.db).list_stock_ledger(transaction_type=AUTOCOUNT_PUSH)

    assert listed.pagination.total == 1, listed
    entry = listed.data[0]
    assert entry.transaction_type == AUTOCOUNT_PUSH
    assert (entry.previous_quantity, entry.new_quantity, entry.quantity_change) == (5, 8, 3)
    assert entry.created_by_name == "ZZTSB admin"
    bulk = StockService(env.db).list_stock_ledger(transaction_type="BULK_IMPORT")
    assert bulk.pagination.total == 0
