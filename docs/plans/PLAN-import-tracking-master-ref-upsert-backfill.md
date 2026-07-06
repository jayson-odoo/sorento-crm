# PLAN — Import-tracking master-ref upsert + backfill (customer & transporter)

**Status:** IMPLEMENTED (Part A + B + tests) — backfill not yet run on prod. Uncommitted.
**Owner:** Claude
**Date:** 2026-07-06

## Problem

Prod loads delivery orders via **Actions → Import tracking** (`import_excel_tracking`, RQ task).
That path writes `debtor_name` / `debtor_code` / `transporter` as free-text but **never**
populates the `customer_id` / `transporter_id` FKs — so new debtors and transporters never
land in the `customers` / `transporters` master tables. Symptom reported: new customers from
DOs missing from Customers table.

Root cause: the master-ref upsert helper `_sync_order_master_refs` (added with FK refactor
migrations 200/206/207/220) is called by `create_order` / `update_order` (API routes) but was
never wired into the Excel import path.

### Flow matrix (verified)

| Flow | customer upsert | transporter upsert | complaint reconcile | live in prod? |
|---|:---:|:---:|:---:|---|
| `create_order` (API) | ✅ | ✅ | ✅ | yes (single create) |
| `update_order` (API) | ✅ | ✅ | ✅ | yes (edit) |
| `import_excel_tracking` (RQ) | ❌ **gap** | ❌ **gap** | ✅ already fires | **yes — the "Import tracking" button** |
| `bulk_import_orders` | ❌ | ❌ | ❌ | **dead** — dialog unreachable, no button calls `setUploadDialogOpen(true)` |

`bulk_import_orders` is dead code (FE `TemplateUploadDialog` never opened). Out of scope; optionally rip out later.

## Fix

### Part A — wire upsert into `import_excel_tracking`

`order_service.py`, method `import_excel_tracking`:

1. **Master sheet — existing-order update branch** (~2282, before the `setattr` loop):
   `mapped = self._sync_order_master_refs(mapped)` so `customer_id` (+ `transporter_id` if
   master carries it) is applied via the existing `for key,value in mapped.items(): setattr(...)`.

2. **Master sheet — new-order branch** (~2301, before `Order(**mapped)`):
   `mapped = self._sync_order_master_refs(mapped)`.

3. **Overall Tracking sheet branch** (~2360, before the `setattr` loop):
   `mapped = self._sync_order_master_refs(mapped)` — the tracking sheet is where `transporter`
   lives (`tracking_mapping["Transporter"] = "transporter"`), so this is what populates
   `transporter_id`.

`_sync_order_master_refs` is idempotent + only acts on truthy `debtor_name` / `transporter`
keys present in the dict, so calling it on both sheets is safe (master mapped has debtor,
tracking mapped has transporter; neither disturbs the other).

**No new helper needed** — reuse `_sync_order_master_refs`, `_upsert_customer_from_debtor`,
`_upsert_transporter_from_text` verbatim (same dedupe rules as API path).

### Part B — backfill existing orphans

Idempotent JOIN-based script (per backfill rule: "set to correct value where mismatch", re-runnable).

`scripts/backfill_order_master_refs.py`:
- For every `orders` row with non-blank `debtor_name` and `customer_id` NULL (or mismatched):
  find-or-create customer via the SAME pair-match rule as `_upsert_customer_from_debtor`
  (`lower(btrim(customer_code))` + `lower(btrim(customer_name))`, blank code → `DBR-<md5>`),
  set `customer_id`.
- For every `orders` row with non-blank `transporter` and `transporter_id` NULL (or mismatched):
  find-or-create transporter by `normalized_name = lower(btrim(transporter))`, set `transporter_id`.
- Reuse the service helpers by instantiating `OrderService(db)` and calling the private
  upsert methods per distinct text value (cache resolved ids in a dict to avoid N queries).
- Dry-run flag (`--dry-run`) prints counts without commit; real run commits in batches.
- Idempotent: re-run only touches rows still NULL/mismatched.

## Out of scope
- `bulk_import_orders` (dead) — leave as-is this PR.
- Complaint reconcile — already fires in `import_excel_tracking`, untouched.

## Verification
- **pytest:** unit test `import_excel_tracking` with a Master row carrying a brand-new debtor +
  a Tracking row with a brand-new transporter → assert a `customers` row and a `transporters`
  row are created and the order FKs point at them. Re-run same import → no duplicate rows (idempotent).
- **Backfill test:** seed orders with free-text debtor/transporter + NULL FKs → run backfill →
  assert master rows created + FKs set; second run = 0 changes.
- **Manual (prod-shaped):** Import tracking Excel with a new debtor + transporter via the UI,
  confirm rows appear in Customers + Transporters lists.

## Worker note
`import_excel_tracking` runs in the RQ worker (`app/tasks/import_tasks.py`). After editing
`order_service.py`, **restart the Worker session** (no reload) before testing.
