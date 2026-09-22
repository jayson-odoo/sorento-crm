# UAC: AutoCount pull preview perf

Plan: `PLAN-autocount-pull-preview-perf.md`. Verified by pytest (CI) + one clone measurement.

| ID | Criterion | Verified by |
| --- | --- | --- |
| PP-1 | A real (non dry-run) ingest of a product whose incoming columns all equal the stored row issues no UPDATE on `products`, leaves `updated_at` / `updated_by` untouched and writes no audit row. | T1, T8 |
| PP-2 | A real ingest of a product with at least one differing column updates it, bumps `updated_at`, stamps `updated_by` when `stamp_user_id` is set, and writes the audit row. | T2 |
| PP-3 | `RecordResult.diff` is populated on real runs: `{}` for unchanged, field map for changed, `None` for created. | T3 |
| PP-4 | Pull apply summary distinguishes `updated` from `unchanged`; unchanged records get no "Product updated" outcome row. | T4 |
| PP-5 | Category / brand / default UOM lookups are resolved once per distinct code per batch. | T5 |
| PP-6 | A reference created inside a record that later fails is never served from cache. | T6 |
| PP-7 | Adoption still links the integration reference even when the record has no column changes. | T7 |
| PP-8 | Parity gate PC-5 and every existing ingest / pull suite stay green. | pytest |
| PP-9 | Clone `sorento_acpull_e2e`, 11,876 SRT products dry-run: <= 90 s (baseline 260 s), numbers recorded in the PR body with statement counts before/after. | `scripts/measure_pull_preview.py` |
| PP-10 | Contract unchanged: `IngestOutcome` values, `/api/v1/ingest/*` response shapes and CONTRACT_VERSION untouched. | `test_ingest_contract_v2.py`, reviewer |
