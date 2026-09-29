# UAC - Ingest stock_balances push (contract 2.5)

- AC-SB-1 `GET /external/contract` answers `version: "2.5"`, lists `stock_balances` in `entities`,
  `warehouse_inactive` in `warnings`, and `fields_added` names `stock_balances`.
- AC-SB-2 A new (product, active warehouse) pair is `created`, `entity_id` is the new stock row id,
  `quantity_on_hand = qty`, reserved and damaged 0.
- AC-SB-3 An existing pair is `updated`; only `quantity_on_hand` changes. A pre-set
  `quantity_reserved`, `quantity_damaged`, `reorder_point` and `zone_id` stay exactly as they were.
- AC-SB-4 Same record twice: second is `updated`; dry run of it shows diff `{}`.
- AC-SB-5 Location matches trimmed + case-insensitive (`" mbs "` finds `MBS`).
- AC-SB-6 Unknown location -> `updated` + `warehouse_unresolved`, `entity_id` null, no row written.
- AC-SB-7 Inactive warehouse -> `updated` + `warehouse_inactive`, no row written or changed.
- AC-SB-8 Unknown item code -> `retryable`, nothing written. Item code with spaces and quotes
  resolves when the product exists.
- AC-SB-9 Missing `item_code` / `location_code`, `qty` string, float, bool or negative -> `failed`
  with `errors`; `qty: 0` is accepted and written as 0.
- AC-SB-10 Unknown extra key -> `failed` (extra forbid); `item_description` and `uom_code`
  accepted and ignored, absent is fine.
- AC-SB-11 Company scoping: a warehouse or product of another company never resolves; the stock row
  created carries the anchored company.
- AC-SB-12 Dry run: identical verdicts, nothing written; created has no diff, changed update has
  `{"qty": {"current", "incoming"}}`; real run carries no diff.
- AC-SB-13 Duplicate pair in one batch: in order, last value wins, verdicts `created` then `updated`.
- AC-SB-14 Summary is `{total, created, updated, failed, retryable}`; every input record gets one
  verdict echoing its `source_ref`.
- AC-SB-15 Deletions: resolvable pair in active warehouse with a row -> `deleted`, qty 0, row kept,
  reserved/damaged untouched; already 0 -> `deleted` again.
- AC-SB-16 Deletions: missing `pairs` entry, unknown product, unknown warehouse, no stock row ->
  `not_found`; inactive warehouse -> `not_found` + `warehouse_inactive`, row untouched.
- AC-SB-17 Deletions: malformed entry -> `failed`; `pairs` not an object -> 422 `INVALID_BODY`;
  `pairs` over `MAX_BATCH` -> 413; dry run writes nothing.
- AC-SB-18 Permissions: a key without `inventory.stock.edit` gets 403 on ingest; without
  `.delete` gets 403 on deletions; migration grants `.view/.edit/.delete` to
  `integration_foundryx_esb`.
- AC-SB-19 Read-back returns `{records: [{source_ref, qty}], not_found}` for pairs.
- AC-SB-20 Corrected A7 fixtures: every request replays against a seeded chain and the response
  matches outcome, warnings and summary (entity_id asserted present or null only).
- AC-SB-21 withdrawn: SR5b dropped by owner ruling 25 Sep 2026 (plan D12).
