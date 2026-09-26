# PLAN - Ingest stock_balances push (contract 2.5, Foundryx SR5)

Status: SR5a built, review READY (reviewer + security-reviewer), PR open; joint run with Foundryx pending. SR5b dropped by owner ruling 25 Sep 2026. Added in review: migration sb2 creates the stock (product_id, warehouse_id) unique index prod lacks.

Source brief: Foundryx plan 13, Appendix A (`foundryx-shared-service` worktree s51,
`documentation/plans/sprint-5/13-autocount-stock-push.md`). Seven corrections were agreed with the
shared-service session on 25 Sep 2026 and are folded in below. Fixtures: that worktree's
`documentation/plans/sprint-5/13-fixtures/` (being re-recorded to the corrected envelope).

## Journey

The Foundryx owner flips AutoCount stock for a company from Pull to Push. From then on Foundryx
posts per-pair stock balance deltas and per-pair zeroings. Sorento's `stock.quantity_on_hand`
follows AutoCount without anyone pressing Pull or importing an Excel file. n8n and the chatbot keep
reading the `stock` table.

## Decisions

- D1. `stock_balances` is a new entity on the existing `/external/ingest` surface. It is not a
  master, document or shipping order, so it gets its own small service
  (`app/services/stock_balance_ingest_service.py`) with its own `STOCK_BALANCE_ENTITIES` set folded
  into `SUPPORTED_ENTITIES`, the same way `SHIPPING_ORDER_ENTITIES` is. The route branches to it
  in `ingest_masters`, `delete_records` and `read_current_state`.
- D2. `CONTRACT_VERSION = "2.5"`. `FIELDS_ADDED` names the new entity. `WARNINGS` gains
  `warehouse_inactive`. `warehouse_unresolved` is reused.
- D3. Upsert row: `{source_ref, item_code, item_description?, location_code, uom_code?, qty}`,
  `extra="forbid"`. `item_description` and `uom_code` are accepted and ignored. `source_ref` is the
  echo key only, never stored.
- D4. Resolution order per record, inside the anchored company:
  1. validation (missing/blank `item_code` or `location_code`, `qty` not a JSON integer (bool
     rejected), `qty < 0`) -> `failed` with `errors`;
  2. `location_code` against `warehouses.warehouse_code`, trimmed + case-insensitive, company-scoped
     (same rule as `classify_stock_rows`): unknown -> `updated` + `warehouse_unresolved`, nothing
     written, `entity_id` null; inactive -> `updated` + `warehouse_inactive`, nothing written;
  3. `item_code` against `products.product_code`, trimmed + case-insensitive, company-scoped (the
     import's rule): not found -> `retryable`, nothing written;
  4. upsert `stock` for (product, warehouse): set `quantity_on_hand = qty` ONLY. Never touch
     `quantity_reserved`, `quantity_damaged`, `reorder_point`, `zone_id`. New row = `created` with
     column defaults and `company_id` = anchored company. Existing row = `updated`, including an
     unchanged value. `entity_id` = stock row UUID. `updated_at` set on a write.
- D5. Each record in its own savepoint, like the master service. One commit per batch. Records are
  processed in input order, so a duplicate pair in a batch ends with the last value.
- D6. Dry run: same verdicts, nothing written. Diff only on dry run. Created -> no diff. Updated with
  no change -> `{}`. Updated with change -> `{"qty": {"current": n, "incoming": m}}`.
- D7. Deletions: `POST /external/ingest/stock_balances/deletions` with `source_refs` and `pairs`
  (`{ref: {item_code, location_code}}`). Body-level: `pairs` absent or not an object, or more than
  `MAX_BATCH` entries -> 422 `INVALID_BODY` / 413 `BATCH_TOO_LARGE`, same as `codes`. Per ref:
  malformed entry -> `failed`; no entry, or product / warehouse / stock row missing -> `not_found`;
  inactive warehouse -> `not_found` + `warehouse_inactive`; otherwise set `quantity_on_hand = 0`,
  keep the row -> `deleted` (again `deleted` when already 0). Never hard-delete, never
  `deactivated`. Dry run writes nothing.
- D8. Read-back (`POST /external/read/stock_balances`): optional, implemented because the entity
  set drives the route. Takes `source_refs` + `pairs`, returns `{records: [{source_ref, qty}],
  not_found: [...]}`.
- D9. Permissions: ingest `inventory.stock.edit`, read `inventory.stock.view`, delete
  `inventory.stock.delete`. Migration grants `.view`, `.edit`, `.delete` to
  `integration_foundryx_esb`.
- D10. Envelopes unchanged: ingest summary `{total, created, updated, failed, retryable}`, deletions
  summary `{total, deleted, deactivated, not_found, failed}`. No `warningCounts`.
- D11. No stock ledger rows, no per-row audit beyond the generic SQLAlchemy audit listeners.
  No Stock List xlsx on this path.
- D12. SR5b DROPPED (owner ruling 25 Sep 2026, via the shared-service session). Stock Pull and the
  manual stock Excel import stay visible and working for every company; the owner does not use
  them on pushed companies. No `stock_pushed_at`, no mode read. Pull keeps its 409 `PUSH_ACTIVE`
  handling unchanged.

- D13. Follow-up fix (small fix track, 26 Sep 2026): the chatbot stock "Data last updated"
  footer read only the system-wide last BULK_IMPORT, and a push writes no ledger row (D11) and
  skips `updated_at` on an unchanged value, so it never moved. Every non-dry batch with at least
  one accepted record (ingest `created`/`updated`, deletions `deleted`) now stamps
  `companies.stock_push_confirmed_at` (migration sb3), and `StockService.list_stock` stamps each
  row with its own company's latest of (last BULK_IMPORT, last push batch).
  Tests: `tests/test_stock_last_updated_push.py`.

## Slices

- SR5a BE: D1-D11, one migration (grants), pytest against the corrected A7 fixtures.
- SR5b: dropped (D12).

## Test list (Phase 2, tester writes first)

See `ingest-stock-balances-2-5-acceptance-criteria.md`; every AC has at least one pytest.

## Trigger for more machinery

None. A second stock-like pushed quantity (e.g. reserved) would be the case that pays for
generalising D4.
