# PLAN: AutoCount pull preview - cut the dry-run ingest time

Status: planned (owner go 22 Sep 2026, "let's optimize our part"). Track: focused lane, backend only, no migration.
UAC: `autocount-pull-preview-perf-acceptance-criteria.md`.
Follows: `PLAN-autocount-pull-review.md` (SR1 preview), `PLAN-ingest-products-code-wins.md` (SR0).

## Problem (measured)

Prod SRT products pull, 22 Sep 2026, 11,724 rows: created 09:18, `started_at` 09:26 (FoundryX build,
their side), finished 09:36. The 10 minutes from `started_at` to finished are ours:
`preview_autocount_pull` -> `MasterIngestService.ingest(..., dry_run=True)` walks the rows ONE at a
time and each existing product costs roughly twelve DB round trips plus three ORM listeners:

| step (`master_ingest_service.py`) | statements |
| --- | --- |
| `begin_nested` per record (`:787`) | SAVEPOINT + RELEASE |
| `_product_columns` -> `product_rules.ensure_reference` category (`:537`) and brand (`:559`) | 2 SELECT, never cached across records |
| `self.refs.resolve` (`:872`) | 1 SELECT |
| `resolve_master_by_code` (`:899`) | 1 SELECT |
| `self.refs.origin_of` (`:901`) | 1 SELECT |
| `_finalize_product_derived` (`:994`) | 1 SELECT |
| `_diff` (`:1136`, dry run only) | 1 SELECT |
| `_update` (`:1163-1174`) | ORM SELECT + flush = UPDATE, and the audit `before_flush`, embedding `after_update` and product spec listeners fire - **even when nothing changed** |
| `link_default_supplier` (`:1064`) | 1 SELECT (+ INSERT) |

In the 21 Sep rehearsal 11,762 of 11,842 records were unchanged, so almost every UPDATE plus its
listeners was wasted. Clone measurement 20 Sep: 11,876 records in 260 s (46 rec/s, rate decays
82 -> 48 as the session's identity map grows). Prod: ~20 rec/s.

Side defect fixed by the same change (finding F-C, 21 Sep rehearsal): the real apply reports
11,821 `updated` and bumps `updated_at` / `updated_by` on every product although the preview
said 59 changed, because `_diff` runs only in dry run and `_update` always writes.

## Design (simplest thing that works, in order; stop when the UAC target is met)

C1. **No write when nothing changed.** `_diff` runs on real ingests too (one SELECT, which the
    UPDATE it replaces already cost). When the diff is `{}`, `_update` is skipped: no ORM load,
    no flush, no listeners, `updated_at` / `updated_by` untouched. `_link` (adoption) and
    `_post_write_product_hooks` still run - both are idempotent and the Excel path applies the
    default-supplier link on every row too. `RecordResult.outcome` stays `UPDATED` (the push
    contract does not change); `diff == {}` is the "unchanged" signal, exactly what
    `_preview_products` already reads. `_apply_products` in `autocount_pull_tasks.py:229` adopts
    the same rule: an updated record with an empty diff is counted `unchanged`, gets no
    "Product updated" outcome row, and the apply summary carries an `unchanged` count.
    Parity test PC-5 (`tests/test_autocount_pull_sr3*.py`, byte-equal products columns through
    X and I) must stay green; if it compares `updated_at`, exclude that column with a comment
    naming this plan (the Excel importer writes every row; that is the ONE column where the two
    paths now differ on a no-op re-sync, and F-C is the reason).

C2. **Per-batch reference cache.** `MasterIngestService` caches `ensure_reference` results for
    (model, company, normalised code) and `resolve_default_uom` for the batch lifetime (the
    instance already lives exactly one batch - `_settings_cache` is the precedent, perf review
    S6). Only FOUND references are cached: one CREATED inside a record's savepoint is rolled back
    if that record fails, so caching it would hand the next record a dead id. Cache lives on the
    instance, cleared by nothing (one batch = one instance).

C3. **One SELECT for derived + diff** (only if C1 + C2 miss the target): `_finalize_product_derived`
    and `_diff` read the same row; read it once with the four derived columns added to the
    diff's column list and pass the row down.

Deferred, with its trigger named: bulk preloads of product code -> id, refs resolve and origin
maps (3 statements per batch instead of 3 per record) ONLY if the clone measurement after C1-C3
is still above the UAC target. Not built on speculation.

## Measurement harness

`scripts/measure_pull_preview.py`: builds N fake product rows with the existing
`scripts/build_fake_foundryx_data.py` shapes (or reads its JSON), runs
`MasterIngestService.ingest("products", rows, dry_run=True)` against `DATABASE_URL`, prints
records, seconds, rec/s and the SQL statement count (SQLAlchemy `before_cursor_execute`
counter). Run before and after on the clone `sorento_acpull_e2e` (11,876 SRT products, mine).
Baseline to beat: 260 s / 11,876 (20 Sep). Target: <= 90 s on the clone.

## Tests (tester writes red first; `tests/test_ingest_perf_round_5.py` is the query-count precedent)

`tests/test_autocount_pull_preview_perf.py`, Postgres via `tests/_pg_fixture.py`, own seeded
company + category + brand + UOM + products (CI DB is empty):

- T1 real ingest of an UNCHANGED existing product: no UPDATE statement issued on `products`,
  `updated_at` and `updated_by` identical before/after, no new `audit_logs` row for it.
- T2 real ingest of a CHANGED product (description differs): UPDATE issued, `updated_at` bumped,
  `updated_by` = `stamp_user_id`, audit row present, diff names the field.
- T3 `RecordResult.diff` is `{}` for T1 and non-empty for T2 on a REAL run (not dry run).
- T4 `_apply_products` summary: 1 changed + 1 unchanged + 1 created -> `updated` 1, `unchanged` 1,
  `created` 1; only the changed and created rows get an import_job_rows outcome.
- T5 two records sharing a category and a brand: exactly one SELECT each on `product_categories`
  and `brands` for the batch (statement counter).
- T6 a category CREATED by a record that then FAILS (unique conflict) is not served from cache to
  the next record: the next record resolves it again and succeeds.
- T7 adoption (refs miss, code hit, no origin) with an empty diff still links the reference.
- T8 dry-run of 5 unchanged products issues no UPDATE and no INSERT into `audit_logs`.
- Existing: PC-5 parity, `test_ingest_products_code_wins.py`, `test_autocount_pull_sr1/sr3`,
  `test_master_ingest.py` all green.

## Out of scope

FoundryX build time (their plan 11: `maxConcurrentPages`, owner opts the connection in), `/rows`
paging, the spec listener, the stock preview (1.2 s already).

## Rollout

Backend only, no migration, no FE. Pre-PR gate: fetch main, single alembic head (unchanged).
DRAFT PR, never merged without go. After merge the next prod pull shows the new preview time
in Job Summary (`started_at` -> `completed_at`).
