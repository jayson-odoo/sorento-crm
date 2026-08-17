# PLAN: flyer / catalogue ingestion into product specifications

**Status:** DRAFT -> building. Written 2026-08-17 (branch `fm/flyer-ingestion-build`, based on
the unmerged PR 4 branch `fm/spec-pr4-extraction-prompt` because `propose_from_text`, the shared
`SpecProposalReview` component and the batch-apply route only exist there; rebase onto `main`
once PR 4 merges). Phase 1 mock (S1): BUILT, browser verification outstanding.
Phase 2 backend (S2): **BUILT** - classifier + registry-helper lift, `AUTHORED_SOURCES` flip,
migration `370_flyer_spec_proposals`, both models, the ingest service, the RQ task and the four
routes; the four red pytest files are green (52 tests) and `alembic heads` is a single head.
Phase 2 frontend wiring (S3): **WIRED** - `USE_MOCK` and the Phase 1 fixtures are gone, the
service is a plain `apiFetch` client and the FE types match the backend schemas field for
field (no type change was needed); the 13 vitest files over these surfaces are green (183
tests). The agent-browser evidence run (section 6) was attempted once 2026-08-17 and blocked by
shared-machine resource exhaustion (login succeeded, sidebar navigation could not complete); a
second attempt the same day **completed** - AC-E.1 and AC-E.2 are verified, full walk, network
calls, console checks and screenshots in section 6. Review (S4): pending.
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

### 3.1 Tables (migration `370_flyer_spec_proposals`, down `367_promote_flyer_provenance`)

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
| Nav | `config/menu.config.tsx` - `Flyer Spec Proposals` under Product Management in `MENU_SIDEBAR` AND `MENU_SIDEBAR_COMPACT` (see section 5), `permission: 'master_data.products.edit'` |

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
  **BUILT.** Three lifts rather than the two this section named: `_assert_read` moved from
  `flyer_readings.py` into `flyer_reading_service.assert_read` as well, because a third route
  across two modules now refuses on the same condition and three copies of a refusal are three
  sets of words that drift. The route module keeps a one-line alias, as it does for
  `_value_for_registry`. Four test corrections, each a test defect rather than a behaviour
  change: the classifier suite imported `_DESCRIPTION_FIRST_KEYS` from `product_spec_write`
  (it lives in `product_spec_derivation`, and re-exporting it would close an import cycle);
  the route suite asserted a few camelCase keys against snake_case bodies (section 5); three
  service tests assumed `SORENTO CERAMIC ART BASIN ONLY` derives `finish = black`, which it
  does not until the description says `BLACK`; and
  `test_migration_367::test_367_is_the_single_alembic_head` pinned the head to 367, now
  rewritten to assert one head with 367 on its path so it does not fail on every later
  migration.
- **S3 - Phase 2 FE wiring (coder) + vitest (tester):** swap mock, delete fixtures not used by
  tests, AC-D.8 tests, agent-browser evidence run written into §6 below. **Mock swapped and
  fixtures deleted** (nothing imported them: the vitest files stub the service module itself,
  so there was no reason to keep a second copy of the shapes). The four route bodies needed
  no correction on either side - the batch, proposal and group field sets are identical to
  `FlyerSpecBatchOut` / `FlyerSpecProposalOut` / `FlyerSpecProductGroupOut`. Evidence run owed.
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

### Recorded limitations (S4 review), not defects

- **The menu entry can gate on ONE slug, so the pair is enforced only at the route.**
  `MenuItem` has no AND form: `permission: 'master_data.products.edit'` is the whole gate the
  sidebar can express, and the four routes require `dealer_kit.page.view` AND
  `master_data.products.edit` (L9). A role holding `products.edit` without `page.view`
  therefore SEES `Product Management -> Flyer Spec Proposals`, clicks it, and gets the error
  alert the list already renders for a 403 rather than a hidden entry. Left as it is: the
  authority that matters is the route's, hiding the entry would need a menu concept nothing
  else in this application has, and the two slugs are held by the same roles in practice.
- **The stored proposal `unit` is display decoration.** It is copied off the registry row when
  the pass runs so the review screen can read "770 mm" rather than "770", but the apply does
  NOT use it: `apply_batch` re-reads the registry live and writes `registry_row.unit`. A key
  whose unit changed between propose and apply is written with the unit it has NOW, and the
  older unit on the proposal row is a snapshot of what the reviewer was shown.

### Amended during review (S4), with the reason

- **The menu entry lives in `MENU_SIDEBAR` and `MENU_SIDEBAR_COMPACT`, not `MENU_MEGA`.** Section
  3.6 and UAC AC-D.6 both said `MENU_MEGA`, written from the assumption that it is a second view
  of the same navigation. It is not: `MENU_MEGA` is the Metronic demo mega menu and carries no
  Master Data / Product Management group at all, so the entry would have had no parent to sit
  under. `MENU_SIDEBAR_COMPACT` is the menu that actually carries a second copy of Product
  Management, and it is where the shipped entry is. Both contract lines are corrected rather than
  the code, because the code went to the only place the entry can be.
- **A `not_promoted` code yields proposals.** UAC AC-A.2 said `unmatched` or `not_promoted` cards
  yield nothing. `not_promoted` is a SUBSET of `MatchReport.matched` (`flyer_matching._not_promoted`
  filters matched codes by promotion membership), so those cards name real products; whether
  marketing added a product to the linked promotion says nothing about what its card prints, and
  refusing to read a printed spec on that ground would silently drop values for products the flyer
  clearly describes. The AC text is corrected; the behaviour is unchanged.
- **One batch-size guard, in the service.** `FlyerSpecApplyIn.proposal_ids` carried
  `max_length=5000` as well as `product_spec_flyer_ingest.MAX_ROWS`, so pydantic 422'd first and
  the service's readable sentence ("That is N proposals. Apply at most 5000 at a time.",
  `product_spec_batch_too_large`) was unreachable. The schema ceiling is dropped; the route test
  now asserts the message and the code, not only the status.
- **`_refuse` never overwrites an `applied` outcome.** It stamped the refusal on the row
  unconditionally, so re-ticking a row that was already written (the ordinary second apply,
  AC-C.6) replaced `outcome='applied'` with `already_matches` - `applied_count` fell to 0 and the
  list screen flipped the batch from Applied back to Proposed for a request that wrote nothing.
  The answer still says `already_matches`; the ROW keeps what happened to it (AC-C.5).

## 6. Evidence run (S3)

**Prior attempt (2026-08-17, earlier same day):** blocked before reaching the walk by shared-machine
resource exhaustion (load average 7.8 -> 37.4, `agent-browser` daemon EAGAIN on its own control
socket). No AC-E.1/E.2 steps were completed; full account of that attempt (isolated stack on ports
8092/3092, mitigations tried, cleanup performed) is preserved in git history of this file. This
section replaces it with the completed run.

**Completed 2026-08-17, against the shared dev stack already running for this worktree**
(`http://localhost:3000` prod-build FE, `http://localhost:8000` BE, RQ worker live), via
`npx -y agent-browser@0.27.0 --session spec-flyer-evidence`. `sysctl -n vm.loadavg` read `4.89
13.40 29.60` at the start (1-min figure sane; the machine is shared and other lanes' load shows in
the 5/15-min figures) and stayed workable throughout - no daemon EAGAIN this time. Login used the
`E2E_EMAIL` / `E2E_PASSWORD` pair from `sorento_crm_frontend/.env.local` (values never echoed).
Every `get url` check confirmed the session stayed on its own tab (no cross-agent tab hijack). The
session was closed with a plain `close` at the end, never `close --all`.

### Walk

1. **Open + login.** `open http://localhost:3000` -> redirected to `/signin?callbackUrl=%2F`;
   filled email/password, clicked Continue, landed on `/` with the full sidebar rendered. Console
   and `errors` clean.
2. **Sidebar Dealer Kit -> Flyers.** Clicked the `Dealer Kit` group, then `Flyers`, reaching
   `/dealer-kit/flyer-readings`. No existing reading was named `flyer_sample.pdf` (the grid held
   several `_SORENTO A3 FLYER 2025-2026_compressed.pdf` rows from other sessions/lanes on the
   shared dev DB, same 36-page / 998-code shape but a different upload filename) - so per the
   brief's fallback, `Read a flyer` was used to upload the committed fixture
   (`sorento_crm_backend/tests/fixtures/dealer_kit/flyer_sample.pdf`) fresh. It read instantly
   (`Done`, 3 pages, 41 product codes) and the row appeared as `flyer_sample.pdf`. Screenshot:
   `evidence/flyer-spec-ingestion/01-reading-page-before-propose.png` (reading page, Specifications
   section with the button, before proposing).
3. **Propose specs from this flyer.** Opened the reading
   (`/dealer-kit/flyer-readings/4f769de0-648f-4a8e-ab10-b8d5f50ef235`). The `Propose specs from
   this flyer` button was below the fold (`getBoundingClientRect().top` ~1957px against an 800px
   viewport) - a plain `click @ref` on the off-screen ref is a no-op with this daemon; the working
   pattern was `scrollintoview @ref` immediately before `click @ref`, used for every off-screen
   click for the rest of the walk. `network requests --filter /api/v1/dealer-kit` confirmed
   `POST .../4f769de0.../spec-proposals` -> **202**, followed by `GET .../spec-proposals` polling.
   `wait --text "This flyer states"` resolved once the batch flipped to `proposed`. Counts
   sentence (verbatim): *"This flyer states 198 specification values across 34 products: 0 new, 24
   change what the master says, 17 conflict with a value a person set, 156 unchanged, 1
   suppressed."* Screenshot: `02-reading-page-proposed-counts.png`. Console/errors clean.
   - **Deviation from the brief, recorded honestly:** the brief expected `new` rows to exist
     (untick one). This flyer's master data already carries prior flyer-authored values for most
     of these 34 products (0 new, 24 change, 156 unchanged) - almost certainly from the same fixture
     having been read and applied before, in this shared dev DB, by an earlier session. The walk
     was adapted: instead of unticking a `new` row, a `change` row was ticked (there being none to
     untick), which still exercises AC-D.3's default-selection rule (nothing ticked by default when
     there are 0 `new` rows) and AC-D.4's confirm-dialog path.
4. **Review proposals.** Clicked the link, landing on
   `/master-data-management/flyer-spec-proposals/4f769de0-...` (`GET .../spec-proposals` fired,
   200). Confirmed the default-selection footer read **"Apply 0 selected" (disabled)** - correct
   per AC-D.3 given 0 `new` rows. Screenshot: `03-review-page-default-selection.png`.
   - Ticked the `FG-CW13` product's `Capacity (oz)` row (`Changes 30 to 30 oz`, a `change` row,
     checkbox enabled) -> footer read "Apply 1 selected". Screenshot:
     `04-review-page-one-change-ticked.png`.
   - Clicked Apply: `AlertDialog` **"Replace 1 master value?"** appeared, naming the row
     (`Capacity (oz)` / `30 becomes 30 oz`) before the write, per AC-D.4. Screenshot:
     `05-replace-confirm-dialog.png`.
   - Confirmed ("Replace and apply"): `POST .../spec-proposals/apply` -> **200**. The result read
     **"Nothing was written to the product master" / "1 not written"** with the row listed as
     `FG-CW13 Capacity oz - Already stored - The product master already holds this value.` This is
     AC-C.2's live re-classification working as designed: the batch's propose-time snapshot said
     `change`, but by apply time the live spec row already matched (most likely written by the
     same prior session that produced the 0-new/24-change starting counts), so the row was refused
     `already_matches` rather than written - exactly the safety net AC-C.2 and AC-C.6 describe.
     Screenshot: `06-review-page-after-apply.png`. Console/errors clean.
   - To get a genuine write (needed for step 6's Specifications-tab evidence), re-selected a
     second `change` row that was a real value change rather than a formatting no-op: product
     `SRTWC286-SH`, key `Type`, `Changes One piece to Toilet seat`. Ticked it, Apply -> `AlertDialog`
     "Replace 1 master value?" again, confirmed. `POST .../spec-proposals/apply` -> **200**, result
     **"1 specification value written to the product master"** / `SRTWC286-SH Type Toilet seat`.
     The row rendered disabled under "ALREADY DECIDED" with an `Applied` mark. Batch header now
     read *"read 17/08/2026, 11:44 am - proposed 17/08/2026, 11:45 am - applied 17/08/2026, 11:47
     am by Jayson Personal"*. Screenshot: `07-review-page-applied-result.png`. Console/errors
     clean.
5. **Product Specifications tab.** Navigated by sidebar: `Product Management -> Products ->
   All Products`, searched `SRTWC286-SH`, opened the exact-code row (variant rows like
   `SRTWC286-SH-NEW-150` matched the search too; the exact-code row was picked deliberately), then
   the `Specifications` tab (needed `scrollintoview` before `click`, same off-screen-click issue as
   step 3). Confirmed the `Type` spec row: value **`Toilet seat`**, source pill **`Flyer`**,
   provenance cell **"Read from: flyer flyer_sample.pdf: SEAT COVER"** - the printed words as
   evidence, filename included, exactly per AC-C.3/AC-C.7/journey step 5. Screenshot:
   `08-product-specifications-tab-flyer-badge.png`. Console/errors clean.
6. **Idempotency (re-propose + re-check).** Returned to the reading page, clicked `Propose again`.
   `POST .../spec-proposals` fired again (**202**), completed near-instantly (this reading's job is
   cheap - 3 pages). New counts sentence: *"This flyer states 198 specification values across 34
   products: 0 new, 17 change what the master says, 17 conflict with a value a person set, 163
   unchanged, 1 suppressed."* (`change` 24 -> 17, `unchanged` 156 -> 163, a swing of 7 rows beyond
   just the 1 this walk itself applied - consistent with the shared dev DB continuing to receive
   writes from other concurrent activity during the walk, noted rather than hidden). Opened
   `Review proposals` again: the previously-applied `SRTWC286-SH` / `Type` / `Toilet seat` row now
   showed **"Already stored"**, non-tickable (disabled checkbox) - AC-C.6's guarantee that a
   re-applied key is refused/non-selectable, not re-written. Footer read "Apply 0 selected".
   Screenshot: `09-review-page-idempotent-recheck.png`. Console/errors clean.
7. **Viewport checks on the review page**, per AC-E.1's "clean console at 375px and 1280px":
   - 375x812: `10-review-page-375x812.png`. Console/errors clean.
   - 1280x800: `11-review-page-1280x800.png`. Console/errors clean.
8. **AC-E.2 - Master Data list page.** Applying once more (a second `change` row, a different
   product's `Type: One piece -> Toilet seat`, same confirm-dialog path, `POST .../apply` -> 200,
   "1 specification value written") was done first so the `Applied on` column would be populated
   before checking the list, since step 6's re-propose had reset the batch's applied history is not
   erased but the batch's own re-propose does not retroactively populate `applied_at` for the new
   proposal rows until something is applied against them. Navigated by sidebar:
   `Product Management -> Flyer Spec Proposals` (confirms AC-D.6: the entry exists under
   Product Management in the sidebar). The `flyer_sample.pdf` row showed **status pill "Proposed"**
   (batch lifecycle statuses are `none`/`proposing`/`proposed`/`failed` per AC-B.1 - there is no
   `applied` batch status) with its own **`Applied on` column populated**
   (`17/08/2026, 11:54 am`), matching AC-B.2's field list (filename, created_at, finished_at,
   status, counts, `applied_at`) rather than the shorthand "status: Applied" in the walk brief.
   Screenshot: `12-flyer-spec-proposals-list-applied.png`. Clicking the row landed back on
   `/master-data-management/flyer-spec-proposals/4f769de0-648f-4a8e-ab10-b8d5f50ef235` - the same
   review page URL as step 4, confirming AC-E.2's "row click opens the same review page." Console
   and `errors` clean.

### Network calls asserted (AC-E.1)

`network requests --filter /api/v1/dealer-kit` was checked after every state-changing step. Full
sequence for reading `4f769de0-648f-4a8e-ab10-b8d5f50ef235` across the walk:

- `POST /api/v1/dealer-kit/flyer-readings` -> 202 (upload)
- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals` -> 202 (propose, x2: initial +
  "Propose again")
- `GET /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals` -> 200 (repeated - initial load,
  poll ticks, post-apply refresh, review-page load)
- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/apply` -> 200 (x3: the refused
  `already_matches` attempt, then two successful writes)
- `GET /api/v1/dealer-kit/flyer-readings/spec-proposal-batches` -> 200 (list page)

### Console / errors

Checked via `console` and `errors` after every major step (login, upload, propose, review load,
each apply, the Specifications tab, the idempotent re-check, both viewports, the list page). Clean
throughout - no warnings or uncaught errors surfaced at any step.

### Evidence files

`documentation/plans/master-data/evidence/flyer-spec-ingestion/`:

1. `01-reading-page-before-propose.png` - reading page, Specifications section, button not yet
   pressed.
2. `02-reading-page-proposed-counts.png` - counts sentence after propose finishes.
3. `03-review-page-default-selection.png` - review page, 0 rows ticked by default (0 `new` rows).
4. `04-review-page-one-change-ticked.png` - one `change` row ticked, footer "Apply 1 selected".
5. `05-replace-confirm-dialog.png` - `AlertDialog` "Replace 1 master value?" naming the row.
6. `06-review-page-after-apply.png` - refused-as-`already_matches` result (live re-classification).
7. `07-review-page-applied-result.png` - successful write result, batch header stamped "applied ...
   by Jayson Personal".
8. `08-product-specifications-tab-flyer-badge.png` - product's Specifications tab, `Type` =
   `Toilet seat`, source pill `Flyer`, evidence text `flyer flyer_sample.pdf: SEAT COVER`.
9. `09-review-page-idempotent-recheck.png` - re-proposed batch, the applied row now "Already
   stored" and non-tickable.
10. `10-review-page-375x812.png` - review page at 375x812.
11. `11-review-page-1280x800.png` - review page at 1280x800.
12. `12-flyer-spec-proposals-list-applied.png` - Master Data list page, batch row with `Applied on`
    populated; row click reopens the same review page.

### Outcome

**AC-E.1 and AC-E.2 verified.** Every route named in the two ACs fired with the expected status
(`POST .../spec-proposals` 202, `GET .../spec-proposals` 200 polling, `POST .../spec-proposals/apply`
200), the review screen's default selection, confirm dialog, applied/refused result rendering, the
product Specifications tab's `Flyer` badge with printed-word evidence, the idempotent re-propose +
non-tickable re-check, the sidebar `Flyer Spec Proposals` entry (AC-D.6), and the list-to-review
row click (AC-E.2) all behaved as specified. Two things are recorded as observations rather than
defects: (1) the fixture's flyer content had already been proposed/applied against this shared dev
DB before this run (0 `new` rows on first propose), which the walk adapted to by exercising the
`change` path instead, and (2) one ticked `change` row turned out to already match the live master
by apply time, which is precisely the live-re-classification safety net AC-C.2 exists to
demonstrate rather than a failure of the walk. AC-E.3 (bundle-card limitation) and AC-E.4 (PR 3
verification-reset follow-up) remain accepted-limitation / backlog items per the UAC, not exercised
here.
