# PLAN: flyer / catalogue ingestion into product specifications

**Status:** DRAFT -> building. Written 2026-08-17 (branch `fm/flyer-ingestion-build`, based on
the unmerged PR 4 branch `fm/spec-pr4-extraction-prompt` because `propose_from_text`, the shared
`SpecProposalReview` component and the batch-apply route only exist there; rebase onto `main`
once PR 4 merges). Phase 1 mock (S1): BUILT, browser verification outstanding. Phase 2: pending.
Review: pending.
**UAC:** `flyer-spec-ingestion-acceptance-criteria.md` (the contract; this plan fulfils it).
**Design source:** `firstmate/data/flyer-spec-ingestion/report.md` §3, §5, §7 (read-only report,
2026-08-16). **Parent plan:** `PLAN-spec-authoring-verification.md` (PR 4 amendment, AC-B.18).
**Classification:** CORE, `public` schema, cross-schema FK to `dealer_kit.flyer_reading`.

## 1. Journey

See the UAC `Journey` section - it governs. Short form: upload once (dealer kit, unchanged) ->
press `Propose specs from this flyer` -> the batch is computed in the background and stored ->
review grouped by product on a Master Data page (`new` ticked, `change` unticked, the rest
read-only) -> `Apply N selected` -> every row reported applied or refused -> the specs read
`Flyer` with the printed words as evidence.

## 2. What already exists, and is reused as-is (file:function)

| Need | Reused | Notes |
|---|---|---|
| Upload + background read | `app/api/v1/dealer_kit/flyer_readings.py:upload_flyer_reading` (202), `app/tasks/flyer_read_tasks.py:read_flyer`, `flyer_reading_service.complete_reading` | Not touched. |
| Which cards are products | `app/services/dealer_kit/flyer_reading_service.py:report_for` -> `MatchReport.matched[*]` (`product_id`, `product_code`, `pages`) | Recomputed on every GET by design; the propose job snapshots the mapping into proposal rows. |
| The card's printed words | `flyer_matching._printed_codes(reading)` -> `_Printed.sized_card` / all cards for a code; `FlyerCard.lines` (`flyer_extraction.py:139`) | Text = `" ".join(lines)` over every card carrying the code (a code printed on two pages contributes both). |
| Extraction | `app/services/product_spec_derivation.py:propose_from_text(text, code, rules_by_key=configured_rules(db), scopes_by_key=configured_scopes(db))` | Pure. Rules/scopes loaded ONCE per job, not per code. |
| Kind classification | `app/services/product_spec_extract.py` lines ~118-150 (tombstone / equal / authored / new / description-first / change) | **Lifted** into `classify_spec_proposal(proposed_entry, stored_entry, stored_stamp, key) -> "suppressed" \| "unchanged" \| "conflict" \| "new" \| "change"` in the same module; `extract_spec_proposals` calls it and maps `suppressed -> conflict`, drops `unchanged` (unchanged behaviour). |
| Registry value validation | `app/api/v1/master_data/product_specifications.py:_value_for_registry` | **Lifted** to `app/services/product_spec_registry.py:value_for_registry(row, raw, reject)`; the route module keeps a one-line alias so its two existing callers do not change. |
| The write | `app/services/product_spec_write.py:apply_spec_values(db, product_code, entries, actor=, commit=False)` | One call per product, one commit per request. |
| Two-permission AND, not-read guard, per-row outcome shape | `flyer_readings.py:apply_flyer_dimensions` (`_READ_THE_FLYER`, `_WRITE_THE_MASTER`, `_assert_read`), `dimension_apply_service.py` outcome constants (`ALREADY_MATCHES`, `CONFLICT_NOT_CONFIRMED`) | Same constants reused where the meaning is identical. |
| Review rows | `sorento_crm_frontend/components/spec-proposals/SpecProposalReview.tsx` + `types.ts` | Gains kinds `unchanged` / `suppressed` (not selectable, own pill). Still product-blind. |
| Polling | `app/(protected)/dealer-kit/flyer-readings/hooks/useFlyerReadings.ts` `refetchInterval` pattern (3 s while in flight) | Copied shape for the batch query. |
| Job harness in tests | `tests/_flyer_read.py` (`patch_flyer_read`, `_db=` seam), `tests/_pg_fixture.py` | Same pattern for the propose task. |
| Source badge | `components/spec-table/SpecSourceBadge.tsx` (`flyer: 'Flyer'`) | Its local `AUTHORED_SOURCES` set gains `flyer`. |

## 3. Design (backwards from the journey)

### 3.1 Tables (migration `368_flyer_spec_proposals`, down `367_promote_flyer_provenance`)

`product_spec_flyer_batches` (`CompanyScopedMixin`, company copied from the reading):

| Column | Type | Note |
|---|---|---|
| `id` | UUID PK | |
| `flyer_reading_id` | UUID FK `dealer_kit.flyer_reading.id` ON DELETE CASCADE, **UNIQUE** | one batch per reading (AC-A.5) |
| `status` | VARCHAR(16) NOT NULL, CHECK in (`proposing`,`proposed`,`failed`) | |
| `error_message` | TEXT NULL | |
| `job_id` | VARCHAR(64) NULL | |
| `product_count`, `proposal_count`, `new_count`, `change_count`, `conflict_count`, `unchanged_count`, `suppressed_count`, `applied_count` | INTEGER NOT NULL DEFAULT 0 | |
| `created_by` | UUID NULL | who pressed Propose |
| `created_at`, `finished_at`, `applied_at` | TIMESTAMP (naive UTC, `finished_at`/`applied_at` NULL) | |
| `applied_by` | UUID NULL | latest apply |

`product_spec_flyer_proposals`:

| Column | Type | Note |
|---|---|---|
| `id` | UUID PK | the apply payload names these |
| `batch_id` | UUID FK batches ON DELETE CASCADE, indexed | |
| `product_id` | UUID FK `products.id` ON DELETE CASCADE | snapshot of the match |
| `product_code` | VARCHAR(100) NOT NULL | |
| `pages` | JSONB NOT NULL DEFAULT `[]` | printed on, for ordering + display |
| `spec_key` | VARCHAR(100) NOT NULL | UNIQUE (`batch_id`, `product_id`, `spec_key`) |
| `value` | JSONB NOT NULL | scalar or list, as `propose_from_text` returned it |
| `unit` | VARCHAR(32) NULL | from the registry row |
| `evidence` | TEXT NOT NULL DEFAULT '' | the printed words |
| `kind` | VARCHAR(16) NOT NULL, CHECK in (`new`,`change`,`conflict`,`unchanged`,`suppressed`) | snapshot at propose |
| `stored_value` JSONB NULL, `stored_unit` VARCHAR(32) NULL, `stored_source` VARCHAR(32) NULL | snapshot at propose | |
| `outcome` | VARCHAR(32) NULL | `applied` / `already_matches` / `conflict_not_confirmed` / `product_spec_bad_value` / `product_not_found` |
| `applied_at` TIMESTAMP NULL, `applied_by` UUID NULL | | |

Models in `app/models/product_spec.py` (`ProductSpecFlyerBatch`, `ProductSpecFlyerProposal`).
Downgrade drops both. Two tables because the batch has its own lifecycle (status, error, counts,
applied) and the list page is a list of batches; folding status onto the dealer kit's row would
put master-data lifecycle on another module's table.

### 3.2 Service `app/services/product_spec_flyer_ingest.py` (one module, plain functions)

- `start_batch(db, record, *, user_id) -> ProductSpecFlyerBatch` - `_assert_read` semantics
  (409 `FLYER_NOT_READ_YET` reuse), 409 `FLYER_SPEC_PROPOSING` if a batch is `proposing`, else
  delete existing proposals + reset counts, status `proposing`, commit, enqueue
  `propose_specs_for_flyer(batch_id)` on `FLYER_READ_QUEUE` via `queue_service.enqueue_job`
  through a module-level `_enqueue(batch)` seam (tests patch it, exactly like
  `flyer_reading_service._enqueue`); on enqueue failure mark `failed` with the message.
- `run_propose(db, batch_id) -> dict` - the job body: load batch + reading (company scope
  narrowed to the reading's company); `report_for(db, record)`; `configured_rules(db)` /
  `configured_scopes(db)` once; registry index once (`spec_key -> row`); spec rows for all matched
  product ids in one query; per matched code: text from the cards, `propose_from_text`, drop
  `origin == "code"`, keep only keys in the registry index, `classify_spec_proposal`, build the
  row; bulk insert; counts; `proposed`. Any exception -> `failed` + `error_message`, never raise.
- `batch_for(db, record) -> ProductSpecFlyerBatch | None`, `list_batches(db)`,
  `grouped_proposals(db, batch) -> list[dict]` (page-ordered product groups).
- `apply_batch(db, batch, *, proposal_ids, user) -> ApplyResult` - AC-C.1..C.6: cap 5000, ids
  in batch, group by product, live re-classify each against the current spec row (same helper),
  refuse `unchanged` -> `already_matches`, `conflict`/`suppressed` -> `conflict_not_confirmed`,
  build entries with `value_for_registry`, ONE `apply_spec_values(..., commit=False)` per product
  inside `try/except AppException` (refuse that product's rows with the message), stamp outcomes,
  batch `applied_*`, one commit.

### 3.3 Task `app/tasks/flyer_spec_propose_tasks.py`

`propose_specs_for_flyer(batch_id: str, *, _db=None) -> dict` - `SessionLocal()` (or `_db`), scope
off, delegate to `run_propose`, `finally` close. Same queue as the read (`flyer_read`), no new
worker config. Worker restart needed locally after adding it (RQ has no reload).

### 3.4 Routes (`app/api/v1/dealer_kit/flyer_spec_proposals.py`, included from
`dealer_kit/__init__.py`; all `Depends(_READ_THE_FLYER), Depends(_WRITE_THE_MASTER)`)

| Method + path | Returns |
|---|---|
| `GET /flyer-readings/spec-proposal-batches` | `list[FlyerSpecBatchOut]` (declared first) |
| `POST /flyer-readings/{reading_id}/spec-proposals` | 202 `FlyerSpecBatchOut` |
| `GET /flyer-readings/{reading_id}/spec-proposals` | `FlyerSpecProposalsOut` = batch (or `status: "none"`) + `groups` |
| `POST /flyer-readings/{reading_id}/spec-proposals/apply` | 200 `FlyerSpecApplyOut` (`applied`, `refused`) |

Schemas in `app/schemas/dealer_kit.py`, **snake_case field names, NOT the dealer kit's camelCase
aliases** (amended in Phase 1, see §5). Body `FlyerSpecApplyIn { proposal_ids: list[UUID] (min 1,
max 5000) }` - `extra="forbid"` so a `values` field is 422.

The batch summary carries three fields this section did not originally name, because the list page
(AC-D.6) and the reading-page section (AC-D.1) have no second call to get them from: `filename`
and `read_at` off the reading, and `created_by_name` / `applied_by_name` resolved to NAMES rather
than ids (AC-B.3). `status` additionally takes the value `none` on the per-reading GET only.
The Phase 1 contract block at the top of `flyerSpecProposalService.ts` is the exact shape; Phase 2
is held to it.

### 3.5 `AUTHORED_SOURCES` flip

`product_spec_write.py:48` -> `frozenset({"human", "supplier", "flyer"})`; update the comment
(the flip has landed, after migration 367). Consequences (AC-C.7): `_prepare` accepts it; a
flyer value is authored for merge / status / boost. FE `SpecSourceBadge.tsx:50` set gains
`flyer`. Tests asserting the old membership are updated, each with the reason.

### 3.6 Frontend

Contract block at the top of
`app/(protected)/master-data-management/flyer-spec-proposals/services/flyerSpecProposalService.ts`.

| Piece | Path |
|---|---|
| Service | `.../flyer-spec-proposals/services/flyerSpecProposalService.ts` - `listFlyerSpecBatches()`, `getFlyerSpecProposals(readingId)`, `proposeFlyerSpecs(readingId)`, `applyFlyerSpecProposals(readingId, proposalIds)` |
| Hooks | `.../flyer-spec-proposals/hooks/useFlyerSpecProposals.ts` - `useFlyerSpecBatchesQuery`, `useFlyerSpecProposalsQuery(readingId)` (3 s poll while `proposing`), `useProposeFlyerSpecs(readingId)`, `useApplyFlyerSpecProposals(readingId)` (invalidate the proposals + batches keys, toast counts applied rows) |
| Mocks (Phase 1) | `.../flyer-spec-proposals/__mocks__/flyerSpecProposals.fixtures.ts` |
| List page | `.../flyer-spec-proposals/page.tsx` + `components/FlyerSpecBatchesList.tsx` (DataGrid, mirrors `brands/components/BrandsList.tsx` shape) |
| Review page | `.../flyer-spec-proposals/[readingId]/page.tsx` + `components/FlyerSpecReviewScreen.tsx` (header, product groups, sticky apply bar, `AlertDialog` for changes, `ApplyResult` table) + `components/ProductProposalGroup.tsx` (code, name, pages, per-product select-all, `SpecProposalReview`) |
| Reading page section | `app/(protected)/dealer-kit/flyer-readings/components/SpecProposalSection.tsx`, rendered from `MatchReportSections.tsx` beside `DimensionReviewSection` |
| Shared component | `components/spec-proposals/types.ts` kind union + `selectableKinds` prop + `SpecProposalReview.tsx` (pill mapping, per-row selectability) |
| Counts sentence | `.../flyer-spec-proposals/lib/countsSentence.ts` - one sentence, read by BOTH the reading-page section and the review header |
| Nav | `config/menu.config.tsx` - `Flyer Spec Proposals` under Product Management in `MENU_SIDEBAR` AND `MENU_MEGA`, `permission: 'master_data.products.edit'` |

Selection: page state `Set<proposalId>` initialised to all `new` ids on first `proposed` load;
per-product select-all toggles that product's `new` + `change` ids. Products render 25 per page
client-side (a "Show more" button), selection survives across.

## 4. Phases and slices

- **S1 - Phase 1 (FE mock, coder):** everything in 3.6 against fixtures; the service returns the
  fixtures behind a `USE_MOCK` const. BUILT. The agent-browser walk (sidebar clicks:
  Dealer Kit -> Flyers -> a reading; Master Data -> Product Management -> Flyer Spec Proposals) at
  375 and 1280 is **still owed** - it was scheduled to a later slice by the orchestrator and no
  stack was started for S1.
- **S2 - Phase 2 backend, test-first (tester red, coder green):** classifier lift + registry
  helper lift + `AUTHORED_SOURCES` flip; migration + models; service; task; routes; schemas.
- **S3 - Phase 2 FE wiring (coder) + vitest (tester):** swap mock, delete fixtures not used by
  tests, AC-D.8 tests, agent-browser evidence run written into §6 below.
- **S4 - Review:** `reviewer` agent + `/code-review`, then an independent Codex review of the
  final diff; findings fixed by the coder; then no-mistakes.

## 5. Decisions and deviations

- Proposals STORED, grouped by PRODUCT: captain brief 2026-08-17 (report §5.4 proposed
  compute-on-read grouped by key; the brief supersedes it, and stored rows are what a batch list
  and a per-row `outcome` need).
- Verification-reset preview (report §5.6.2) deferred to after PR 3: no verification model on
  main; the reset itself is the choke point's job (UAC AC-E.4). Backlog row added.
- `unchanged` and `suppressed` shown as read-only rows (brief), where PR 4 omits/merges them:
  the counts sentence and the idempotency evidence need them visible.
- No de-duplication of a re-uploaded PDF (`sha256`) in this slice - it is a reading-layer
  concern (report §5.7 row 1) and orthogonal to proposing.
- The bundle-card guard (report §3.5) is not built: reviewed proposals plus per-row evidence
  contain it (UAC AC-E.3).

### Amended during Phase 1 (S1), with the reason

- **snake_case bodies, not the dealer kit's camelCase aliases** (§3.4 as written). These payloads
  carry `spec_key` / `stored_value` / `data_type` rows straight into `components/spec-proposals`,
  which is a product-specification component and speaks snake_case, as does every other spec
  endpoint. A camelCase batch wrapping snake_case rows is two conventions in one response, and the
  UAC names every field of these four routes in snake_case (AC-B.1, AC-B.2, AC-C.1).
- **`conflict` selectability is a PROP on the shared component, not a rule inside it.** §3.6 said
  the shared component gets "non-selectable rows for the two new kinds"; making non-selectability a
  property of the kind alone also froze `conflict`, which the pasted-text panel (PR 4) deliberately
  lets a person tick while looking at ONE product - its own test caught it. So
  `SpecProposalReview` takes `selectableKinds`, defaulting to `['new','change','conflict']` (PR 4
  unchanged), and the flyer surface passes `['new','change']` (L6/L7). `unchanged` and `suppressed`
  are refused whatever is passed - there is no value to write for either.
- **Applied and refused rows leave the table** rather than rendering as disabled rows inside it
  (AC-D.4 "applied rows render disabled with an `Applied` mark"). A stored proposal keeps its
  `outcome`, so after an apply those rows move to an "Already decided" strip under the same product
  card carrying an outcome pill each. Same information, and no tick that cannot do anything - which
  is the rule the sizes section already follows. It also needs no per-row prop on the shared
  component.
- **The apply response has no `applied_count` / `refused_count`.** AC-C.1 names the two arrays and
  nothing else, and the screen counts what it renders, so the counts cannot disagree with the list.
- **`MatchReportSections` gains an optional `readingStatus`** (default `done`) so the section can
  say "Read the flyer first" (AC-D.1) rather than offer a button that cannot work. Optional because
  the only caller renders that component after the read is done and the existing tests pass no such
  prop.
- **The Phase 1 mock is a small in-memory STORE**, not four frozen fixtures: none -> proposing ->
  proposed and the second apply of an applied batch (AC-C.6) are the states that matter most here,
  and a frozen fixture can show the ends but none of the moves. Five seeded readings
  (`flyer-mixed`, `flyer-empty`, `flyer-failed`, `flyer-proposing`, `flyer-none`, matched by suffix
  too) make every state reachable from the list, and pressing Propose on any real reading walks the
  transition. Deleted in S3.

## 6. Evidence run (S3) - to be filled by the tester

_(steps, network calls, screenshots at 375/1280, console clean, second apply all `already_matches`)_
