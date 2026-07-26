"""Ingest AutoCount stock-balance reports as run-history snapshots — Slice 4.

A stock balance is a report, not a document: one array, no DocKey, one row per
Item x Location x UOM x Batch, balances signed. Semantics differ from the
masters/documents ingest on every axis, so it gets its own service:

  * NOT idempotent-by-key: each ingest is a *run*, appended, so the balance at
    different points in time is preserved and comparable in the UI;
  * NOT integration_references: a report row has no stable identity to link;
  * resolution is best-effort: an unresolvable ItemCode/Location keeps its raw
    code and leaves product_id/warehouse_id NULL -- a report legitimately lists
    items that have not synced, and dropping them would misreport the balance.

Returns a run summary, not a per-record verdict: the caller pushed a report, not
a batch of records to quarantine individually.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.canonical_masters import CanonicalStockBalanceRow

logger = logging.getLogger(__name__)


class StockBalanceIngestService:
    def __init__(self, db: Session, integration_id: Optional[str] = None):
        self.db = db
        self.integration_id = integration_id

    def ingest(self, rows: list[dict]) -> dict:
        # Validate every row up front: a report is ingested whole (one run), so a
        # malformed row fails the run rather than silently landing a partial
        # snapshot the caller believes is complete.
        parsed: list[CanonicalStockBalanceRow] = []
        errors: list[dict] = []
        for i, raw in enumerate(rows):
            try:
                parsed.append(CanonicalStockBalanceRow(**raw))
            except (ValidationError, TypeError) as exc:
                errors.append({"index": i, "error": str(exc)})
        if errors:
            return {"created": False, "errors": errors, "row_count": 0}

        run_id = str(uuid.uuid4())
        self.db.execute(
            text(
                "INSERT INTO stock_balance_snapshot_runs (id, row_count, source) "
                "VALUES (:id, :n, 'autocount')"
            ),
            {"id": run_id, "n": len(parsed)},
        )

        resolved_products = 0
        for row in parsed:
            product_id = self._lookup("products", "product_code", row.item_code)
            warehouse_id = (
                self._lookup_warehouse(row.location_code) if row.location_code else None
            )
            if product_id:
                resolved_products += 1
            self.db.execute(
                text(
                    "INSERT INTO stock_balance_snapshots "
                    "(id, run_id, product_id, warehouse_id, item_code, location_code, uom, batch_no, "
                    " balance, smallest_bal_qty, standard_cost, total_cost, average_cost, rate, description) "
                    "VALUES (:id, :run_id, :product_id, :warehouse_id, :item_code, :location_code, :uom, "
                    " :batch_no, :balance, :smallest_bal_qty, :standard_cost, :total_cost, :average_cost, "
                    " :rate, :description)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "item_code": row.item_code,
                    "location_code": row.location_code,
                    "uom": row.uom,
                    "batch_no": row.batch_no,
                    "balance": row.balance,
                    "smallest_bal_qty": row.smallest_bal_qty,
                    "standard_cost": row.standard_cost,
                    "total_cost": row.total_cost,
                    "average_cost": row.average_cost,
                    "rate": row.rate,
                    "description": row.description,
                },
            )

        return {
            "created": True,
            "run_id": run_id,
            "row_count": len(parsed),
            "rows_with_product": resolved_products,
            "rows_without_product": len(parsed) - resolved_products,
        }

    def _lookup(self, table: str, column: str, value: str) -> Optional[str]:
        row = self.db.execute(
            text(f"SELECT id FROM {table} WHERE {column} = :v LIMIT 1"), {"v": value}
        ).first()
        return str(row[0]) if row else None

    def _lookup_warehouse(self, code_or_name: str) -> Optional[str]:
        # Location resolves by warehouse code OR name (AutoCount sends the code,
        # but some feeds send the display name).
        row = self.db.execute(
            text(
                "SELECT id FROM warehouses WHERE warehouse_code = :v OR warehouse_name = :v LIMIT 1"
            ),
            {"v": code_or_name},
        ).first()
        return str(row[0]) if row else None
