"""Stock "Data last updated" reflects the AutoCount `stock_balances` push (#1257).

The chatbot footer "_Data last updated: ..._" is the MCP envelope's
`last_updated_at`, walked out of every row's `updated_at` (and the payload's
own `last_updated_at` in the summary visibility modes). It used to be the
SYSTEM-WIDE latest BULK_IMPORT ledger time, but the push writes no ledger row
and skips `updated_at` on an unchanged value, so a push every 5 minutes never
moved it. Owner: "when i ask, i expect the last updated to be now so it is
real time to the user".

Pinned here:

* an accepted push batch moves the time even when every row is unchanged,
  and a zeroing (deletions) batch does too; a dry run does not;
* the time is per company: the latest of that company's last BULK_IMPORT and
  its last push batch, so a Mocha answer never borrows Sorento's push;
* SYSTEM_ADJUSTMENT zeroing still does not count.

Postgres only, blank schema, every row seeded here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards.
from app.main import app  # noqa: E402,F401

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import StockLedger
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.inventory_service import StockService
from app.services.stock_balance_ingest_service import StockBalanceIngestService

from tests._mc_lookup_seed import MOCHA_ID, product, seed_mocha, stock, warehouse
from tests._pg_fixture import blank_session

# The footer the owner saw frozen: 25/09/2026 17:38:50 MYT = 09:38:50Z.
OLD_IMPORT = datetime(2026, 9, 25, 9, 38, 50)


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _ledger(db, *, company_id, product_id, warehouse_id, txn="BULK_IMPORT", when=OLD_IMPORT):
    db.add(
        StockLedger(
            id=str(uuid.uuid4()),
            product_id=product_id,
            warehouse_id=warehouse_id,
            transaction_type=txn,
            quantity_change=5,
            previous_quantity=0,
            new_quantity=5,
            company_id=company_id,
            created_at=when,
        )
    )
    db.flush()


def _stocked(db, company_id, *, qty=5):
    """A product + warehouse + stock row, last imported at OLD_IMPORT."""
    wh = warehouse(db, company_id=company_id)
    p = product(db, company_id=company_id)
    stock(db, company_id=company_id, product_id=p.id, warehouse_id=wh.id, on_hand=qty)
    _ledger(db, company_id=company_id, product_id=p.id, warehouse_id=wh.id)
    db.commit()
    return p, wh


def _push(db, company_id, p, wh, *, qty=5, dry_run=False):
    service = StockBalanceIngestService(db, company_id=company_id)
    result = service.ingest(
        "stock_balances",
        [
            {
                "source_ref": f"ZZTLU:{uuid.uuid4().hex[:8]}",
                "item_code": p.product_code,
                "location_code": wh.warehouse_code,
                "qty": qty,
            }
        ],
        dry_run=dry_run,
    )
    if not dry_run:
        db.commit()
    return result


def _row_times(result):
    return {str(s.product_id): s.updated_at for s in result["data"]}


def test_push_batch_with_only_unchanged_rows_moves_the_footer(db):
    p, wh = _stocked(db, DEFAULT_COMPANY_ID, qty=5)
    before = StockService(db).list_stock(product_ids=[p.id])
    assert _row_times(before)[str(p.id)] == OLD_IMPORT

    started = datetime.utcnow() - timedelta(seconds=1)
    result = _push(db, DEFAULT_COMPANY_ID, p, wh, qty=5)  # same value: a no-op write
    assert result.records[0].outcome.value == "updated"

    after = StockService(db).list_stock(product_ids=[p.id])
    stamped = _row_times(after)[str(p.id)]
    assert stamped >= started, (stamped, started)


def test_dry_run_push_does_not_move_the_footer(db):
    p, wh = _stocked(db, DEFAULT_COMPANY_ID, qty=5)
    _push(db, DEFAULT_COMPANY_ID, p, wh, qty=9, dry_run=True)

    after = StockService(db).list_stock(product_ids=[p.id])
    assert _row_times(after)[str(p.id)] == OLD_IMPORT


def test_zeroing_push_batch_moves_the_footer(db):
    p, wh = _stocked(db, DEFAULT_COMPANY_ID, qty=5)
    started = datetime.utcnow() - timedelta(seconds=1)
    service = StockBalanceIngestService(db, company_id=DEFAULT_COMPANY_ID)
    ref = "ZZTLU:zero"
    result = service.delete(
        [ref],
        pairs={ref: {"item_code": p.product_code, "location_code": wh.warehouse_code}},
    )
    db.commit()
    assert result.records[0].outcome.value == "deleted"

    after = StockService(db).list_stock(product_ids=[p.id])
    assert _row_times(after)[str(p.id)] >= started


def test_per_company_answers_use_that_companys_time(db):
    seed_mocha(db)
    sorento_p, sorento_wh = _stocked(db, DEFAULT_COMPANY_ID)
    mocha_p, _ = _stocked(db, MOCHA_ID)
    # Mocha's own last import is older still, so a system-wide max would be wrong
    # for it even before any push.
    mocha_import = OLD_IMPORT - timedelta(days=2)
    db.query(StockLedger).filter(StockLedger.company_id == MOCHA_ID).update(
        {StockLedger.created_at: mocha_import}
    )
    db.commit()

    started = datetime.utcnow() - timedelta(seconds=1)
    _push(db, DEFAULT_COMPANY_ID, sorento_p, sorento_wh)

    mocha_only = StockService(db).list_stock(product_ids=[mocha_p.id])
    assert _row_times(mocha_only) == {str(mocha_p.id): mocha_import}

    sorento_only = StockService(db).list_stock(product_ids=[sorento_p.id])
    assert _row_times(sorento_only)[str(sorento_p.id)] >= started

    both = _row_times(StockService(db).list_stock(product_ids=[sorento_p.id, mocha_p.id]))
    assert both[str(mocha_p.id)] == mocha_import
    assert both[str(sorento_p.id)] >= started


def test_company_push_time_outranks_an_older_import_but_not_a_newer_one(db):
    p, wh = _stocked(db, DEFAULT_COMPANY_ID)
    pushed = datetime(2026, 9, 26, 1, 0, 0)
    db.query(Company).filter(Company.id == DEFAULT_COMPANY_ID).update(
        {Company.stock_push_confirmed_at: pushed}
    )
    db.commit()
    assert _row_times(StockService(db).list_stock(product_ids=[p.id]))[str(p.id)] == pushed

    newer_import = pushed + timedelta(hours=1)
    _ledger(db, company_id=DEFAULT_COMPANY_ID, product_id=p.id, warehouse_id=wh.id, when=newer_import)
    db.commit()
    assert _row_times(StockService(db).list_stock(product_ids=[p.id]))[str(p.id)] == newer_import


def test_system_adjustment_zeroing_still_does_not_count(db):
    p, wh = _stocked(db, DEFAULT_COMPANY_ID)
    _ledger(
        db,
        company_id=DEFAULT_COMPANY_ID,
        product_id=p.id,
        warehouse_id=wh.id,
        txn="SYSTEM_ADJUSTMENT",
        when=OLD_IMPORT + timedelta(days=1),
    )
    db.commit()
    assert _row_times(StockService(db).list_stock(product_ids=[p.id]))[str(p.id)] == OLD_IMPORT


def test_summary_mode_payload_time_is_the_answered_companys(db):
    """`compact` carries no rows, so the payload states `last_updated_at` itself:
    it must be the answered company's time, not another company's push."""
    from tests.test_stock_visibility_policy import _contact, _policy_row

    seed_mocha(db)
    sorento_p, sorento_wh = _stocked(db, DEFAULT_COMPANY_ID)
    mocha_p, _ = _stocked(db, MOCHA_ID)
    contact = _contact(db)
    _policy_row(db, mode="compact", contact=contact)
    db.commit()

    started = datetime.utcnow() - timedelta(seconds=1)
    _push(db, DEFAULT_COMPANY_ID, sorento_p, sorento_wh)

    mocha = StockService(db).list_stock(product_ids=[mocha_p.id], contact_id=contact.id)
    assert mocha["data"] == []
    assert mocha["last_updated_at"] == OLD_IMPORT

    sorento = StockService(db).list_stock(product_ids=[sorento_p.id], contact_id=contact.id)
    assert sorento["last_updated_at"] >= started
