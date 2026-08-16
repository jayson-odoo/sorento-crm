# RUNBOOK - promote flyer provenance to authored, and retire the flyer surfaces

**Plan:** `PLAN-spec-authoring-verification.md`, PR 4. **UAC:** AC-B.10 to AC-B.14.
**Scope of one deploy:** steps 1 to 4. **Step 5** is run after that deploy is up.
**Step 6 is a LATER, SEPARATE deploy and is NOT executed here.**

Why this is a runbook and not a migration note: the promote migration moves 3,353 provenance
entries on 1,389 rows across 695 product codes, and in the same deploy derivation stops reading
the flyer text. If those two land apart, the next `derive_for_code` on an affected code (fired by
the change listener on any description edit, not only the nightly job) permanently drops every
flyer-only value on that code. That is one-directional data loss, which is what the ordering below
exists to prevent.

Run every command from `sorento_crm_backend/` on the target environment, with `DATABASE_URL`
pointing at the database being migrated. The counting SQL is read-only and safe to run at any
time.

---

## Step 1 - confirm the source-keyed boost branch is present

PR 1 owed PR 4 a branch that boosts by SOURCE rather than by "is it human". Without it, promoting
flyer entries to `source: human` silently demotes 695 codes from the `flyer_source_boost` knob to
a flat 1.0 on exactly the queries they used to win. Do not run step 3 until this passes.

```bash
grep -n 'source_boosts' app/services/product_spec_search.py
```

Expected, and all three lines must be there:

```
823:    source_boosts = {authored: human_source_boost for authored in AUTHORED_SOURCES}
824:    source_boosts["flyer"] = policy.get("flyer_source_boost", 1.0)
955:                weight *= source_boosts.get(source, 1.0)
```

Line 824 is the one that matters: `flyer` keeps its own knob, so the two can be retuned apart, and
line 823 means a promoted entry picks up `human_source_boost` (seeded at 1.5, deliberately equal
to `flyer_source_boost`, so the promotion is ranking-neutral on day one). If line 824 is missing,
stop and land PR 1's branch first.

Confirm the two knobs are actually seeded in this database:

```sql
SELECT policy_key, value FROM product_spec_search_policy
 WHERE policy_key IN ('human_source_boost', 'flyer_source_boost');
```

Both should be present and equal. If `human_source_boost` is absent, PR 1's seed did not run here.

---

## Step 2 - pre-flight dump

Take a data-only dump of the one table the migration writes, before anything else.

```bash
pg_dump "$DATABASE_URL" --data-only --table=product_specifications \
  --file="product_specifications-preflight-$(date -u +%Y%m%dT%H%M%SZ).sql"
```

Keep the file until step 5 has been verified. It is the escape hatch that does not depend on the
downgrade being correct.

---

## Step 3 - pre-flight counts, the checksum, then the migration

### 3a. Pre-flight counts

```sql
-- Provenance entries whose source is the flyer.
SELECT count(*) AS flyer_entries
  FROM product_specifications s
  CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(spec_key, entry)
 WHERE e.entry->>'source' = 'flyer';

-- Rows holding at least one such entry.
SELECT count(*) AS rows_with_flyer
  FROM product_specifications s
 WHERE EXISTS (
   SELECT 1 FROM jsonb_each(s.provenance) AS e(spec_key, entry)
    WHERE e.entry->>'source' = 'flyer'
 );

-- Distinct product codes behind those rows. `product_specifications` is keyed on
-- `product_id`, and a code can have a copy per company, so the code count needs the join.
SELECT count(DISTINCT p.product_code) AS codes_with_flyer
  FROM product_specifications s
  JOIN products p ON p.id = s.product_id
 WHERE EXISTS (
   SELECT 1 FROM jsonb_each(s.provenance) AS e(spec_key, entry)
    WHERE e.entry->>'source' = 'flyer'
 );
```

Expected, measured 2026-08-13 on the copy of production: **3,353 entries, 1,389 rows, 695 codes**.

Re-measured 2026-08-16 on the same copy the same three queries returned **3,351 / 1,389 / 695**.
The two-entry drift is a hand edit in the intervening days, not a defect, and it is recorded here
so an operator who sees 3,351 does not stop. Treat the row and code counts as the load-bearing
ones: a figure that is not within a few entries of 3,353, or a row count that is not 1,389 plus or
minus a handful, means this database is not the one these numbers were taken from. Write down
whatever the three queries actually return before the run, because step 3d compares against them.

### 3b. The `values` checksum, before

The whole point of the migration is that it moves provenance and nothing else. This is what proves
it.

```sql
SELECT md5(string_agg(md5(values::text), '' ORDER BY id)) AS values_checksum
  FROM product_specifications;
```

Record the string. On the copy of production on 2026-08-16 it was
`5afb2727e1e5afe73ee44958cbd88834`; the value is environment-specific, so record the one this
database returns rather than comparing to that.

### 3c. Run the migration

```bash
venv/bin/alembic upgrade head
```

Head at this point is `367_promote_flyer_provenance`, chained onto `366_merge_flyer_promo_scm_heads`
(the empty merge that rejoined the two heads main was carrying). The promote migration logs its
before and after counts through `logging`, so capture the deploy log.

It is mismatch-based and idempotent: it selects rows that still hold at least one `source = 'flyer'`
entry, so a second run updates zero rows and a previous partial run is completed rather than
skipped.

### 3d. Post-run assertions

All three must hold.

```sql
-- 1. Zero flyer entries remain.
SELECT count(*) AS flyer_entries_remaining
  FROM product_specifications s
  CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(spec_key, entry)
 WHERE e.entry->>'source' = 'flyer';
-- expected: 0

-- 2. The same N entries now carry the promotion marker, on the same N rows and codes.
SELECT count(*) AS migrated_entries
  FROM product_specifications s
  CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(spec_key, entry)
 WHERE e.entry->>'migrated_from' = 'flyer';
-- expected: the flyer_entries figure recorded in 3a

SELECT count(*) AS migrated_rows
  FROM product_specifications s
 WHERE EXISTS (
   SELECT 1 FROM jsonb_each(s.provenance) AS e(spec_key, entry)
    WHERE e.entry->>'migrated_from' = 'flyer'
 );
-- expected: the rows_with_flyer figure recorded in 3a

-- 3. The `values` checksum is IDENTICAL to 3b.
SELECT md5(string_agg(md5(values::text), '' ORDER BY id)) AS values_checksum
  FROM product_specifications;
```

A spot check on the re-stamped shape, so the evidence prefix is visible rather than assumed:

```sql
SELECT p.product_code, e.spec_key, e.entry
  FROM product_specifications s
  JOIN products p ON p.id = s.product_id
  CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(spec_key, entry)
 WHERE e.entry->>'migrated_from' = 'flyer'
 LIMIT 5;
```

Each entry should read `{"source": "human", "confidence": <kept>, "evidence": "flyer: <original>",
"migrated_from": "flyer"}`. `values`, `rendered_text` and `derived_hash` are untouched.

If the checksum moved, the migration wrote something it must not have. Stop, restore
`product_specifications` from the step 2 dump, and do not proceed to step 5.

---

## Step 4 - the same deploy also stops derivation reading the flyer, and retires findability

**Steps 2, 3 and 4 are one deploy.** They are listed separately because they are separate
verifications, not because they can ship apart.

Two things ship in the same release as the migration:

- **Derivation stops reading the flyer.** `derive()` and `derive_for_code()` lose their
  `flyer_text` parameter, `derive_all` loses its preload, `_input_hash` loses its flyer part and
  `DERIVATION_VERSION` bumps. The flyer pass itself is lifted, not deleted: it survives as the pure
  `propose_from_text(text, code)` that writes nothing and feeds the proposal path (AC-B.18). The
  reason this cannot lag the migration by even one deploy is at the top of this document.
- **Findability retires.** Its selector filters on `source = 'flyer'`, which the promote migration
  empties. Shipped later, the panel would keep rendering and quietly report a much weaker test
  under the same headline numbers, which is worse than it being gone (AC-B.12). Retired together:
  `PUT /by-product/{id}/flyer-text`, the `flyer_text` field on the `GET /by-product/{id}` response,
  the four `/findability/*` routes, `app/services/spec_findability.py`,
  `app/services/product_flyer_import.py` (zero callers), and on the frontend `FlyerCard`,
  `FindabilityPanel`, the "Flyer check" tab and the matching service functions. No screen is left
  offering a setting that silently does nothing (AC-B.14).

The findability history tables (`product_findability_runs`, `product_findability_results`) and the
`ProductFlyerText` model stay. Dropping them is step 6 and a separate cleanup.

Verify after the deploy that no surface still calls the retired routes:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X PUT \
  "$API_BASE/api/v1/master-data/product-specifications/by-product/<any-product-id>/flyer-text" \
  -H "X-API-Key: $EXTERNAL_API_KEY" -H 'Content-Type: application/json' -d '{"text":"x"}'
# expected: 404

curl -s -o /dev/null -w '%{http_code}\n' \
  "$API_BASE/api/v1/master-data/product-specifications/findability/flyers" \
  -H "X-API-Key: $EXTERNAL_API_KEY"
# expected: 404
```

---

## Step 5 - the full-catalogue re-derive (AC-B.13)

Removing the flyer from the derived-input fingerprint changes `_input_hash` for every code, so the
next derivation rewrites every row rather than skipping on an equal hash. That is an ops task with
its own verification, not a side effect to discover when the nightly job runs long. Run it
deliberately, after the deploy in steps 2 to 4 is up and verified.

### 5a. Record the before counts

```sql
SELECT count(*) AS spec_rows FROM product_specifications;

SELECT status, count(*) FROM product_specifications GROUP BY status ORDER BY 1;

SELECT count(*) AS open_exceptions
  FROM product_spec_exceptions WHERE resolved_at IS NULL;

SELECT reason, count(*) FROM product_spec_exceptions
 WHERE resolved_at IS NULL GROUP BY reason ORDER BY 2 DESC;
```

On the copy of production on 2026-08-16 these read 22,938 rows (3 authored, 22,418 derived, 517
needs_review) and 285 open exceptions (237 `shape_mismatch`, 39 `column_conflict`, 5
`company_copies_disagree`, 3 `implausible_dimension`, 1 `human_override_conflict`). Production will
differ; what matters is the before and after pair from the SAME database.

### 5b. Start the re-derive

Either route runs the same `derive_all` over every code, all companies.

**From the screen (preferred, because it has a status anyone can poll).** Master Data ->
Specifications -> the master spec screen, then "Read the catalogue again". That is
`POST /api/v1/master-data/spec-registry/reread-catalogue`, which calls
`product_spec_rederive.start(db)`. It runs on a background thread inside the API process, refuses
to start a second run alongside the first, and writes the rules fingerprint when it finishes. Poll
it with `GET /api/v1/master-data/spec-registry/catalogue-status` (or just leave the screen open)
until `status` reads `done`. It takes minutes over the whole catalogue.

**On the RQ worker**, when the API process should not carry it:

```python
# app/tasks/product_spec_tasks.derive_product_specs(codes=None, chunk_size=500, run_label=None)
from app.services.queue_service import enqueue_job
from app.tasks.product_spec_tasks import derive_product_specs

enqueue_job(derive_product_specs, queue_name="imports", run_label="flyer-promote-rederive")
```

`codes=None` means the whole catalogue. The queue is `imports`, the same one the spec change
listener uses. The worker has no reload, so restart it after this deploy before enqueuing
anything, or it runs the previous release's derivation code, which still reads the flyer.

### 5c. Record the after counts and compare

Re-run every query in 5a.

- **Row count** should be unchanged. Derivation rewrites rows, it does not create or delete
  product copies. A change here means codes appeared or disappeared for an unrelated reason, and
  is worth explaining before moving on.
- **Status counts** may move, and the direction to expect is `derived` and `needs_review`
  shuffling as values that only ever came from the flyer stop being re-derived. The 3 `authored`
  rows are a floor, not a ceiling: promoted rows whose status the migration lifted from `derived`
  to `authored` are counted from step 3, not here.
- **Exception counts** are the number to watch, and the expected rise is measured rather than
  guessed. Flyer-only values are now authored, and an authored value that a rule disagrees with
  raises `human_override_conflict` (AC-B.16, D8) instead of being overwritten. A rise in that one
  reason is the intended consequence of promotion, not a regression. A rise in `shape_mismatch` or
  `implausible_dimension` is not, and should be investigated.

  **Expect about 464 new `human_override_conflict` rows, on 464 spec rows** - the count goes from
  1 to roughly 465. That is a replay of the promote plus the re-derive against the copy of
  production, not an estimate. Nearly all of them are `finish`, where the code suffix reads one
  colour and the description word reads another, so the promoted flyer value and the rule now
  disagree in the open. The number is here so an operator can tell 464 from 4,640: an order of
  magnitude more means something other than the promotion moved, and is worth stopping for.

Record both sets in the PR or the deploy log. AC-B.13 is satisfied by the pair being written down,
not by the re-derive merely having run.

---

## Step 6 - drop `product_flyer_text` (a LATER, SEPARATE deploy - NOT part of this PR)

Do not run this with steps 1 to 5. It ships only once steps 3 and 5 have been verified in
production and the catalogue has been observed for long enough that nobody wants the old card text
back.

1. Its own dump first:

   ```bash
   pg_dump "$DATABASE_URL" --data-only --table=product_flyer_text \
     --file="product_flyer_text-preflight-$(date -u +%Y%m%dT%H%M%SZ).sql"
   ```

2. Confirm nothing reads it any more:

   ```bash
   grep -rn --include='*.py' -e 'ProductFlyerText' -e 'product_flyer_text' sorento_crm_backend/app
   ```

   After steps 3 and 4 the only remaining hits should be the model definition itself. If anything
   else appears, that surface was missed in step 4.

3. Then, and only then, the drop migration and the model deletion.

The findability history tables (`product_findability_runs`, `product_findability_results`) belong
to this same later cleanup. Their rows stay readable until then, which is why step 4 removes the
endpoints but not the tables.

**This step is NOT revertible.** Once the card text is dropped, the only copy is the dump.

---

## Revert

**Steps 1 to 4 are revertible. Step 6 is not.**

To undo the promotion, go back exactly one revision:

```bash
venv/bin/alembic downgrade 366_merge_flyer_promo_scm_heads
```

`366_merge_flyer_promo_scm_heads` is the empty merge revision immediately below
`367_promote_flyer_provenance`, so this runs the promote migration's `downgrade()` and nothing
else. That downgrade is exact: every entry carrying `migrated_from = 'flyer'` goes back to
`{"source": "flyer", "confidence": <kept>, "evidence": <the "flyer: " prefix stripped>}`, and
`status` returns to `derived` on a row that reads `authored` and holds no other authored entry.
`values`, `rendered_text` and `derived_hash` were never touched, so there is nothing to restore in
them.

Verify the revert with the same two queries:

```sql
SELECT count(*) AS flyer_entries
  FROM product_specifications s
  CROSS JOIN LATERAL jsonb_each(s.provenance) AS e(spec_key, entry)
 WHERE e.entry->>'source' = 'flyer';
-- expected: the flyer_entries figure recorded in 3a

SELECT md5(string_agg(md5(values::text), '' ORDER BY id)) AS values_checksum
  FROM product_specifications;
-- expected: identical to 3b, as it was after 3d
```

Two things the downgrade does not undo, and both need the code rolled back with it:

- Derivation no longer reads the flyer. Reverting the migration alone puts the provenance back but
  leaves the running release ignoring `product_flyer_text`, so the next `derive_for_code` on an
  affected code drops the restored values again. Roll back the application release together with
  the migration.
- Step 5's re-derive has already rewritten `derived_hash` on every row. Nothing is lost by that,
  but the rows will re-derive again on the way back, so budget the same minutes for the return
  trip.

If the downgrade is not trusted for any reason, the step 2 dump restores `product_specifications`
outright and does not depend on the migration being correct in either direction.
