# DEPLOY - project sales module (`feat/project-lead-to-so`)

What has to be RUN on production for this branch, beyond `alembic upgrade head`. Everything
here is idempotent and safe to re-run; each entry says how to tell whether it did anything.

## 1. Retire provisional rows superseded before reconciliation shipped

**Script:** `sorento_crm_backend/scripts/backfill_retire_superseded_order_inquiry_rows.py`
**When:** AFTER the app containers carrying commit "reconcile provisional and AutoCount
numbers on ingest" are live. Order matters only in that running it earlier fixes fewer rows;
it never conflicts.

`project_so_ingest_service._reconcile_core_order` merges the Order Inquiry sheet's provisional
`sales_orders` row with AutoCount's real-numbered one AT INGEST TIME. Documents ingested
before that shipped were never reconciled, so both rows stay open and `scm.committed_v` counts
that demand twice, permanently - nothing re-runs the ingest for them. The script finds those
pairs and merges them exactly as the service would: closes the provisional header and its
lines, stamps `Retired: superseded by <doc no>`, moves the still-unresolved SO<->PO link
claims onto the real number, and repoints `project_sales_orders.so_id` under the service's own
guard (a link a person made by hand is left alone).

```bash
# in the backend container / checkout, from sorento_crm_backend/
python scripts/backfill_retire_superseded_order_inquiry_rows.py            # DRY RUN (default)
python scripts/backfill_retire_superseded_order_inquiry_rows.py --apply    # write
```

- **Dry run is the default.** Nothing is written without `--apply`.
- **Read the dry run before applying.** It prints one line per pair:
  `<provisional number> -> <real number>  [project]`, and marks any pair whose two rows sit in
  DIFFERENT companies as `SKIPPED` - those are never merged, by design (a double count is a
  reporting error, a cross-company link is a breach).
- **Idempotent.** The match is "the provisional row is still `open` while a real-numbered row
  exists", so a row it already retired stops matching. A second run reports nothing, and a
  partial first run is corrected rather than compounded.
- **Verifying afterwards:** the same dry run should report `pairs examined: 0`.

Local development database at the time of writing: **0 pairs** (3 `project_sales_orders` rows,
none carrying an `autocount_doc_no`), so both the dry run and the apply were no-ops there. The
production count is expected to be non-zero and must be read from the dry run before applying.
