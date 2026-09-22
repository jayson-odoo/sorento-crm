# UAC: AutoCount pull preview perf

Plan: `PLAN-autocount-pull-preview-perf.md`. Verified by pytest (CI) + one clone measurement.

| ID | Criterion | Verified by |
| --- | --- | --- |
| PP-1 | A real (non dry-run) ingest of a product whose incoming columns all equal the stored row issues no UPDATE on `products`, leaves `updated_at` / `updated_by` untouched and writes no audit row. Holds too when a same-batch record has already linked the same product via adopt/create (fix round). | T1, T8, T12, T13 |
| PP-2 | A real ingest of a product with at least one differing column updates it, bumps `updated_at`, stamps `updated_by` when `stamp_user_id` is set, and writes the audit row. | T2 |
| PP-3 | `RecordResult.diff` is populated on real runs: `{}` for unchanged, field map for changed, `None` for created. A discontinued -> live product's diff names the `discontinued_notified_at`/`discontinued_notify_batch_id` watermark reset (fix round). | T3, TestDiscontinuedWatermarkInPreviewDiff |
| PP-4 | Pull apply summary distinguishes `updated` from `unchanged`; unchanged records get no "Product updated" outcome row. A second same-batch adopter of the same product by a normalize-equal code still reaches UPDATED with `ref_mismatch`, not FAILED (fix round, B1/B2). | T4, T12 |
| PP-5 | Category / brand / default UOM lookups are resolved once per distinct code per batch. Product code/ref/origin/default-supplier resolution is bulk-preloaded once per BATCH, not once per record (round 2), survives a chunked preload and a same-batch create-then-duplicate-code or rename-via-ref (fix round). | T5, T9, T9b, T10, T11, T13, T14, T15, TestDefaultUomResolvedOncePerBatch |
| PP-6 | A reference created inside a record that later fails is never served from cache. Same guarantee for the round-2 code-to-id preload map. | T6, T11 |
| PP-7 | Adoption still links the integration reference even when the record has no column changes. | T7 |
| PP-8 | Parity gate PC-5 and every existing ingest / pull suite stay green. | pytest |
| PP-9 | Clone `sorento_acpull_e2e`, 11,876 SRT products dry-run: <= 90 s (baseline 260 s), numbers recorded in the PR body with statement counts before/after. Round 2's own preload was built because C1-C3 alone measured 157 s on the clone, still short of the target - PP-9 covers both rounds' numbers. | `scripts/measure_pull_preview.py` |
| PP-10 | Contract unchanged: `IngestOutcome` values, `/api/v1/ingest/*` response shapes and CONTRACT_VERSION untouched. A real (non dry-run) ingest's `as_dict()` carries no `diff` key on any record - only a dry run's does (fix round, captain's ruling); `RecordResult.diff` itself stays populated in-process on a real run for `_apply_products`/`_preview_products` to read directly. | `test_ingest_contract_v2.py`, `TestAsDictDiffOnlyOnDryRun`, reviewer |
