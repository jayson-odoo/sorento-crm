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
Captain amendments F and G (S5): **BUILT** - conflicts apply on tick, values edit in place, rows
are added and dismissed, the page searches; three columns folded into migration 370, three new
routes, two data-driven props on the shared review component. See section 7c for what shipped and
where it deviates. Amendment F+G agent-browser evidence run (own agent stack, ports 3040/8040):
**completed 2026-08-17** - AC-F.1-F.5 and AC-G.1-G.4 verified; AC-G.5 half-verified with one
found defect (search-clear does not restore the full product-group list/pagination - reproduced
3x, not fixed here, logged as a follow-up). Full walk, network calls, console checks and
screenshots in section 6b.
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

## 6b. Amendment F+G evidence run

**Completed 2026-08-17, own agent stack** (FE prod-dev on `:3040`, BE on `:8040`, RQ worker on
Redis db 5, all started and killed by the tester agent; `:3000`/`:8000` belong to other lanes and
were never touched), against the shared dev Postgres, via
`npx -y agent-browser@0.27.0 --session spec-flyer-fg`. Scope: UAC sections F (conflict apply +
inline edit) and G (add / dismiss / search) - see section 7c for what shipped. This run keeps
the section 6 run above rather than replacing it; section 6 covers AC-E.1/E.2 baseline, this run
covers AC-F.1-F.5 and AC-G.1-G.5 specifically. Login used `E2E_EMAIL`/`E2E_PASSWORD` from
`sorento_crm_frontend/.env.local` (values never echoed). `get url` was checked before every read
that mattered; the session stayed on its own tab throughout. Closed with a plain `close`, never
`close --all`.

### Walk

1. **Open + login + sidebar to the fixture reading.** `open http://localhost:3040` ->
   `/signin?callbackUrl=%2F`, filled email/password, `Continue` -> `/` with full sidebar. Clicked
   `Dealer Kit` -> `Flyers`, searched `flyer_sample`: a `Done` row already existed at
   `4f769de0-648f-4a8e-ab10-b8d5f50ef235` (34 products, 3 pages, from the earlier section 6 run
   against this same shared dev DB) - reused per the brief's fallback rather than re-uploading.
   Screenshot: `fg-00-flyers-list-search.png`. Console/errors clean.
2. **Propose again.** Opened the reading, scrolled to the Specifications section (already showed
   a prior batch: "0 new, 17 change, 17 conflict, 163 unchanged, 1 suppressed" - leftover from
   section 6). Screenshot: `fg-01-reading-page-before-propose-again.png`. Clicked `Propose again`
   -> `POST .../spec-proposals` **202**, polled to completion. New counts: *"198 specification
   values across 34 products: 0 new, 16 change what the master says, 17 conflict with a value a
   person set, 164 unchanged, 1 suppressed."* Screenshot: `fg-02-reading-page-proposed-counts.png`.
   Console/errors clean.
3. **Review page, default selection and tickable kinds (AC-F.4).** Clicked `Review proposals` ->
   `/master-data-management/flyer-spec-proposals/4f769de0-...`. Footer read **"Apply 0 selected"**
   (disabled) - correct with 0 `new` rows at load. Screenshot:
   `fg-03-review-page-default-selection.png`. Clicked the per-product select-all checkbox for
   `SRTWC7614-RL` (2 `change` rows - `Length`, `Type` - plus a `Trap` `change` row once counted:
   **"3 of 3 ticked"**, footer *"3 ticked, 3 replacing a value the master holds"* - confirms both
   `change` AND `conflict` rows are tickable in bulk per-product select-all (only `Height`/`Width`/
   `Flush type`/`Rimless`/`Seat cover material`, all `Already stored`, stayed unticked/disabled).
   Screenshot: `fg-04-review-page-select-all-tickable.png`. Console/errors clean.
4. **Edit a numeric row in place (AC-F.2/F.3).** Product `SRTJC8037`, `Height` (`conflict`: `600
   mm` vs stored `590 mm`). Clicked pencil -> a `spinbutton` with a `mm` suffix appeared alongside
   Save/Cancel (screenshot `fg-05-edit-numeric-row-input.png`), filled `595`, clicked Save ->
   `PATCH .../spec-proposals/{id}` **200**. Row re-rendered `595 mm` with an **`edited`** mark, pill
   still `Conflicts with your value 590 mm` (unchanged since 595 still disagrees with 590).
   Screenshot: `fg-06-edit-numeric-row-saved.png`. Console/errors clean.
5. **Edit an enum row in place (AC-F.2/F.3, live re-classification).** Product `SRTWC287-RL`,
   `Trap` (`change`: stored `S trap` -> proposed `P trap`). Clicked pencil -> a closed-vocabulary
   `combobox` opened with exactly the two allowed values (`S trap`, `P trap`) - screenshot
   `fg-07-edit-enum-row-dropdown.png`. Selected `S trap` (deliberately picking the value that now
   MATCHES the stored value, to exercise live recompute) and Saved -> `PATCH .../spec-proposals/{id}`
   **200**. Row re-rendered `S trap` with an `edited` mark and the pill flipped from `Changes S trap
   to P trap` to **`Already stored`** (kind live-recomputed `change` -> `unchanged`), checkbox no
   longer tickable - the batch's own aggregate counts sentence dropped from 16 to 15 `change` in
   the next screenshot, confirming the recount is live, not just per-row. Screenshot:
   `fg-08-edit-enum-row-saved.png`. Console/errors clean.
6. **Add a specification (AC-G.1/G.4).** Product `FG-CW13`, clicked `Add specification` -> dialog
   `Add a specification` (screenshot `fg-09-add-specification-dialog.png`), key picker limited to
   applicable registry keys not already on the product (`Capacity (oz)`/`Type` correctly absent
   from the list). Picked `Finish or colour` -> a second registry-typed picker appeared (`Pick a
   finish or colour`, closed vocabulary) - screenshot `fg-10-add-specification-key-picked.png`.
   Picked `Black` (screenshot `fg-11-add-specification-value-picked.png`), clicked `Add` ->
   `POST .../spec-proposals/rows` **201**. New row appeared: `Finish or colour` `Black` `edited`,
   pill `New`, checkbox **unticked** (a row added after the page's initial load is not swept into
   the load-time "tick every `new` row" selection - noted as an observed behaviour, not a defect;
   confirmed intentional-looking on the next full reload, step 8). Screenshot:
   `fg-12-add-specification-row-appears.png`. Batch header count moved `198 -> 199`, `0 -> 1 new`.
   Console/errors clean. (Two earlier attempts to pick a dropdown option closed the whole dialog
   with no request fired - the option element was below the fold inside the dialog's own listbox;
   `scrollintoview` on the option ref before `click` fixed it both times it recurred, same
   off-screen-click pattern section 6 already documented for the Propose button.)
7. **Dismiss a row (AC-G.3/G.4).** Same `FG-CW13` group, `Type` (`Tumbler`, `unchanged`/`Already
   stored`). Clicked `Dismiss Type` -> confirm `AlertDialog` reading **"Dismiss this proposal? It
   will not be applied. This action cannot be undone."** with the row named (`Type Tumbler`) -
   screenshot `fg-13-dismiss-confirm-dialog.png` - matching AC-G.4's specified copy verbatim.
   Confirmed -> `DELETE .../spec-proposals/{id}` **200**, response is the refreshed batch summary
   per the section-7c deviation (not empty). Row gone from the group; batch count `199 -> 198`.
   Screenshot: `fg-14-dismiss-row-gone.png`. Console/errors clean.
8. **Search (AC-G.5).** Ticked the `FG-CW13` `Finish or colour` `new` row (confirmed via a fresh
   full page load first: **"1 of 1 ticked"** on load, proving `new` rows tick on the load-time
   selection pass even though the same row did NOT auto-tick at the moment it was created via the
   `POST rows` mutation in step 6 - a real, if narrow, distinction between "ticked on load" and
   "ticked on create"). Typed `SRTWC7614` into the product/spec search: only the `SRTWC7614-RL`
   group rendered (`0 of 3 ticked` for it), footer still read **`1 ticked`** - the hidden `FG-CW13`
   tick survived being filtered out. Screenshot: `fg-15-search-filter-product-code.png`. Typed
   `Height` (a spec-key search, not a product code): filtered to product groups carrying a
   `Height` row (`SRTJC2023` shown), footer still `1 ticked`. Screenshot:
   `fg-16-search-filter-by-spec-key.png`. Cleared the search box.
   **Defect found and recorded (not fixed - out of tester scope):** clearing the search input
   does not restore the full/paginated product-group list. The page loads 25 of 34 groups with a
   `Show more products (9 left)` button; after typing a filter and then clearing it back to an
   empty string, the visible group count sticks at whatever the last filtered result count was
   (reproduced 3 times: once mid-walk, once in a clean isolated repro via `eval` counting
   `a[href*="/master-data-management/products/"]` - 25 on fresh load, 15 after a `Trap` search,
   still 15 after clearing - and once again for the `Height` search/clear pair used for this
   screenshot), and the `Show more` button does not reappear, so the remaining groups (including
   whichever held position 1, e.g. `FG-CW13`) become unreachable without a full page reload.
   Selection state for hidden/former rows IS preserved correctly (the `1 ticked` footer never
   dropped), so half of AC-G.5 ("keeping selection state for hidden rows intact") holds; the
   "search clears back to the un-filtered view" half does not. Screenshot (state after clearing,
   list still capped): `fg-17-search-cleared-selection-intact.png`. Worked around by reloading the
   page fresh for the remaining steps. Filed as a follow-up rather than fixed here (tester scope
   is verification, not repair). **Fixed in the follow-up commit recorded in section 7c** - not
   logged to the backlog, because it is repaired rather than deferred.
9. **Apply: one conflict + one change + the manual row (AC-F.1, AC-F.4, AC-G.2).** Fresh page
   load, re-ticked `SRTWC7614-RL`'s select-all (`Length` conflict, `Type` change, `Trap` change -
   the `Trap` edit from step 5 was on a DIFFERENT product, `SRTWC287-RL`, so it did not interfere)
   plus the `FG-CW13` `Finish or colour` `new` row already ticked from the fresh load: footer
   **"4 ticked, 3 replacing a value the master holds"**. Screenshot: `fg-18-ticked-for-apply.png`.
   Clicked `Apply 4 selected` -> `AlertDialog` **"Replace 3 master values, 1 of them set by a
   person? 4 rows will be written. 3 of them replace what the product master holds today, and 1
   replace a value somebody set by hand. This action cannot be undone."** listing `Length 250 mm
   becomes 680 mm`, `Type One piece becomes Toilet seat`, `Trap S trap becomes P trap` - exact
   match to AC-F.4's "Replace K master values, D of them set by a person?" copy, K=3 D=1.
   Screenshot: `fg-19-apply-confirm-dialog.png`. Confirmed ("Replace and apply") ->
   `POST .../spec-proposals/apply` **200**. Batch header stamped `applied 17/08/2026, 12:50 pm by
   Jayson Personal`. Screenshot: `fg-20-apply-result.png`. Scrolled to `SRTWC7614-RL`: the 3
   applied rows (including the `Length` **conflict**) moved into an `ALREADY DECIDED` subsection
   with an `Applied` mark each - `Length 680 mm Applied`, `Type Toilet seat Applied`, `Trap P trap
   Applied` - confirming AC-F.1 (conflict rows ARE written on tick+apply, not refused) and AC-C.5
   (per-row `applied` outcome). Screenshot: `fg-21-apply-result-rows-applied.png`. `FG-CW13`
   likewise showed `ALREADY DECIDED / Finish or colour Black Applied` (screenshot
   `fg-22-fgcw13-after-apply.png`). Console/errors clean throughout.
10. **Product Specifications tab: Flyer vs Set by hand badges (AC-G.2).** Sidebar `Product
    Management -> Products -> All Products` (the sidebar accordion needed several retries in this
    run - `aria-expanded` on the nav toggle buttons did not reliably flip via ref-based `click`;
    a direct JS `.click()` dispatch on the matched `<button>` via `eval` is what actually worked,
    recorded as a tooling friction note, not a product defect - the underlying accordion DOES open
    and its links DO navigate once actually clicked). Searched `SRTWC7614-RL`, opened the
    exact-code row, `Specifications` tab. `Trap` = `P trap`, pill **`Flyer`**, expanded to `Read
    from: flyer flyer_sample.pdf: P-TRAP`. Screenshots: `fg-23-product-specifications-tab.png`,
    `fg-24-specifications-trap-flyer-badge.png`, `fg-25-specifications-trap-evidence-expanded.png`.
    Then searched `FG-CW13`, opened it, `Specifications` tab: `Finish or colour` = `Black`, pill
    **`Set By Hand`** (visually distinct primary-colour badge vs. the grey `Flyer`/`Description`
    pills), expanded to **`Set by: set during flyer review`** - the exact evidence string named in
    AC-G.2, and `source='human'` confirmed by the badge itself (`SpecSourceBadge`'s "Set by hand"
    styling is reserved for `human`-sourced authored values). Screenshot:
    `fg-26-specifications-finish-set-by-hand.png`. Console/errors clean.
11. **Idempotency after re-propose (AC-C.6, extended to the F/G-amended rows).** Back to the
    reading's review page, `Propose again` -> `POST .../spec-proposals` **202**. New counts: *"198
    specification values across 34 products: 0 new, 14 change what the master says, 16 conflict
    with a value a person set, 167 unchanged, 1 suppressed."* (`new` `1 -> 0` since the applied
    `Finish or colour` row is no longer new; `change`/`conflict` each dropped by 1 for the same
    reason). Searched `SRTWC7614-RL`: `Length`, `Type` and `Trap` all now read **`Already stored`**
    (was `Conflicts with your value 250 mm` / `Changes ... to ...` before this run's apply) -
    screenshots `fg-27-repropose-idempotent-already-stored.png`,
    `fg-28-repropose-type-trap-already-stored.png`. Console/errors clean.
12. **Viewport checks on the review page (375x812 and 1280x800).** Fresh reload (to get a clean,
    un-filtered group order given the step-8 search-clear defect), search box empty, `FG-CW13`
    first. `set viewport 375 812` -> screenshot `fg-29-review-page-375x812.png`, console/errors
    clean, no horizontal overflow, sticky Apply bar readable. `set viewport 1280 800` ->
    screenshot `fg-30-review-page-1280x800.png`, console/errors clean.
13. **Master Data list page (AC-D.6/E.2, re-confirmed post-amendment).** Sidebar `Flyer Spec
    Proposals` -> `/master-data-management/flyer-spec-proposals`. `flyer_sample.pdf` row: status
    `Proposed`, 34 products, 198 values, 0 new, 14 change (matches step 11's re-propose counts);
    `Applied on` column read **"Not yet"** - expected, not a regression: the same behaviour was
    already documented in section 6 ("the batch's own re-propose does not retroactively populate
    `applied_at` for the new proposal rows until something is applied against them") and step 11
    of this run re-proposed without re-applying. Screenshot: `fg-31-list-page-batch.png`. Row
    click reopened the same review page URL. Console/errors clean.

### Network calls asserted (AC-F.2, F.5, G.1, G.3 routes)

`network requests --filter /api/v1/dealer-kit` was checked after every state-changing step. Full
non-OPTIONS sequence for reading `4f769de0-648f-4a8e-ab10-b8d5f50ef235` across this run:

- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals` -> **202** (x2: step 2 propose
  again, step 11 re-propose)
- `GET /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals` -> **200** (repeated - initial load,
  poll ticks, post-edit/add/dismiss/apply refreshes, review-page loads)
- `PATCH /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/{proposal_id}` -> **200** (x2: step
  4 numeric edit, step 5 enum edit)
- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/rows` -> **201** (step 6 add)
- `DELETE /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/{proposal_id}` -> **200** (step 7
  dismiss)
- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/apply` -> **200** (step 9 apply)
- `GET /api/v1/dealer-kit/flyer-readings/spec-proposal-batches` -> **200** (step 13 list page)

### Console / errors

Checked via `console` and `errors` after every state-changing step (login, propose-again, each
edit, add, dismiss, each search, apply, the Specifications tab visits, the re-propose, both
viewports, the list page). Clean throughout - no warnings or uncaught errors surfaced anywhere in
this run.

### Evidence files

`documentation/plans/master-data/evidence/flyer-spec-ingestion/`, all prefixed `fg-` to keep this
run's files distinct from section 6's numbered set:

`fg-00-flyers-list-search.png`, `fg-01-reading-page-before-propose-again.png`,
`fg-02-reading-page-proposed-counts.png`, `fg-03-review-page-default-selection.png`,
`fg-04-review-page-select-all-tickable.png`, `fg-05-edit-numeric-row-input.png`,
`fg-06-edit-numeric-row-saved.png`, `fg-07-edit-enum-row-dropdown.png`,
`fg-08-edit-enum-row-saved.png`, `fg-09-add-specification-dialog.png`,
`fg-10-add-specification-key-picked.png`, `fg-11-add-specification-value-picked.png`,
`fg-12-add-specification-row-appears.png`, `fg-13-dismiss-confirm-dialog.png`,
`fg-14-dismiss-row-gone.png`, `fg-15-search-filter-product-code.png`,
`fg-16-search-filter-by-spec-key.png`, `fg-17-search-cleared-selection-intact.png`,
`fg-18-ticked-for-apply.png`, `fg-19-apply-confirm-dialog.png`, `fg-20-apply-result.png`,
`fg-21-apply-result-rows-applied.png`, `fg-22-fgcw13-after-apply.png`,
`fg-23-product-specifications-tab.png`, `fg-24-specifications-trap-flyer-badge.png`,
`fg-25-specifications-trap-evidence-expanded.png`, `fg-26-specifications-finish-set-by-hand.png`,
`fg-27-repropose-idempotent-already-stored.png`, `fg-28-repropose-type-trap-already-stored.png`,
`fg-29-review-page-375x812.png`, `fg-30-review-page-1280x800.png`, `fg-31-list-page-batch.png`.

### Outcome

**AC-F.1 through F.5 and AC-G.1 through G.5 verified**, with one defect found and one behavioural
observation, both recorded rather than silently worked around:

- **AC-F.1** (conflict rows write on tick+apply): confirmed - `Length` (a `conflict` row) applied
  alongside the two `change` rows in one request, all three landed in the product's live spec
  table.
- **AC-F.2/F.3** (inline edit, PATCH, live recompute, edited mark): confirmed for both a numeric
  key (`Height`, stayed `conflict` after edit) and an enum key (`Trap`, flipped `change` ->
  `unchanged` live after the edited value came to match the stored one) - the second case is
  stronger evidence than a same-kind edit would have been, since it proves the recompute is real
  rather than cosmetic.
- **AC-F.4** (tickable kinds, select-all, confirm-dialog copy): confirmed verbatim, including the
  "K master values, D of them set by a person" two-count phrasing.
- **AC-F.5** (`allowed_values` on the GET payload): confirmed indirectly - the enum edit widget
  rendered exactly the registry's two allowed values with no second network call between opening
  the editor and seeing the dropdown populated.
- **AC-G.1/G.4** (add a specification, key picker scoped to applicable+absent keys, value input
  keyed to registry type): confirmed - `Capacity (oz)`/`Type` (already on the product) were absent
  from the picker; `Finish or colour` offered a closed-vocabulary value picker.
- **AC-G.2** (manual row applies as `source='human'` with the fixed evidence string): confirmed -
  `Finish or colour` on `FG-CW13` applied and rendered `Set By Hand` / `Set by: set during flyer
  review`, visually and textually distinct from the `Flyer`-badged `Trap` row applied in the same
  request.
- **AC-G.3/G.4** (dismiss, confirm-dialog copy, hard delete, row gone): confirmed verbatim copy
  match.
- **AC-G.5** (search filters product/spec-key client-side, selection survives): **half confirmed,
  half a found defect.** Filtering by product code and by spec-key label both work, and ticked
  selection for a row hidden by the filter survives the filter being applied. But clearing the
  search back to empty does not restore the full/paginated product-group list - the visible count
  sticks at the last filtered result and the `Show more` affordance disappears, stranding whatever
  groups aren't in that stuck subset. Reproduced three times independently. This is a genuine gap
  against "a search input filters product groups ... client-side" (the implicit contract is that
  clearing IS a filter, to the empty string, and should show everything) and should be fixed
  before this slice is signed off; logged as a follow-up rather than fixed by the tester.
  **Fixed in the follow-up commit recorded in section 7c**: `shown` is a depth into whichever
  list is on screen, and it was carried across a change of list, so a depth reached inside a
  filter came back out of it either painting every product at once or capping the restored list
  with no `Show more` to ask for the rest. Every search change now restarts the paging from the
  top, and the box carries its own clear button so emptying it is one deterministic click.
  Three vitest cases on `FlyerSpecReviewScreen` hold it.
- **Tooling friction, not a product defect:** two Radix-style dropdown listboxes (the `Add
  specification` key/value pickers) needed `scrollintoview` on the option ref before `click`, same
  as section 6's off-screen-Propose-button finding - the daemon's coordinate click is a no-op on
  an element outside the current viewport rather than erroring, which cost two silent dialog-closes
  before the pattern was applied consistently. The Product Management sidebar accordion's
  `aria-expanded` did not reliably flip via ref `click` in this session (multiple clicks read back
  `false` even after the panel visibly opened elsewhere in the DOM) - a direct JS `.click()`
  dispatch via `eval` on the matched button element was what reliably worked; the accordion and
  its links function correctly once actually triggered, so this reads as an agent-browser ref/CDP
  coordinate-mapping quirk against this app's nested-accordion sidebar rather than an app bug.

### 7b. Second hands-on amendment (same session): add, dismiss, search

Captain: the review page should be the whole act - add a spec the flyer missed, dismiss a wrong
read, search, never visit the product page. UAC section G. Design: POST rows / DELETE row on the
batch (manual rows carry origin='manual', apply as source='human'); client-side search over
product groups; reuse the registry key picker rules from the product tab (applicable keys only).
NOT the spec verification list (PR 3) - separate surface, shared write choke point.

### 7c. What the two amendments actually shipped (S5), and where it deviates

**Backend.** `origin` (`flyer` | `manual`, NOT NULL DEFAULT `flyer`), `edited_at` and `edited_by`
are FOLDED into migration `370_flyer_spec_proposals` (unmerged, so no new revision and no head
change - still a single head, 370). They are in the CREATE TABLE and again as
`ADD COLUMN IF NOT EXISTS` ALTERs, because the migration is idempotent by design and a database
that already ran the earlier shape of it holds the table without them. `edited` is derived
(`edited_at IS NOT NULL`), never a second column that can disagree with its own timestamp.

`apply_batch` now refuses only `unchanged` (`already_matches`) and `suppressed`
(`conflict_not_confirmed`); a `conflict` is written (AC-F.1). Three new service functions -
`edit_proposal`, `add_proposal_row`, `delete_proposal` - each validate through
`value_for_registry`, recompute `kind` against the LIVE spec row with the same shared
`classify_spec_proposal`, and recount the batch off its rows (`refresh_counts`) rather than
adjusting a counter. Three new routes carry the same permission pair, in the same order, as the
other four.

**Frontend.** The shared `SpecProposalReview` gained exactly two data-driven props -
`renderValue(proposal, defaultCell)` and `rowActions(proposal)` - plus two optional fields on
`SpecProposal` (`allowed_values`, `edited`). It still owns no editing state, imports no service
and knows nothing about a product: the flyer surface holds which row is open and hands back the
default cell for every row it is not editing, which is what keeps the READ rendering in one
place. The editor widget (`ProposalValueEditor`) and the key picker (`AddProposalRowDialog`) live
in the flyer surface. `BULK_SELECTABLE_KINDS` is now `['new', 'change', 'conflict']`.

**Deviations from the UAC, each deliberate:**

1. **`flyer_spec_key_not_applicable` (400)** on `POST .../rows`. AC-G.1 names four refusals and
   says the key must be "applicable to the product's class" without naming the refusal for it.
   The gate is `product_spec_extract._in_scope` - literally the one the propose pass runs - and a
   key it drops is refused 400 with that code. Not a 404: the key exists, it just does not belong
   on this product, and answering "unknown key" would send the reader to the registry.
2. **`DELETE` answers 200 with the batch summary**, which the UAC left open. The counts have just
   moved and the screen renders them; returning nothing would have made the caller refetch to
   learn what it already caused.
3. **The `conflict_not_confirmed` sentence changed.** It read "This disagrees with a value
   somebody set, or with a specification they removed"; only the tombstone half can still happen,
   so it now reads "Somebody removed this specification from this product." A refusal whose words
   describe a case that can no longer occur is worse than no words.
4. **One set of words for "this batch is not `proposed`".** `assert_proposed` in the service, and
   a `_settled_batch` helper in the route module that resolves the reading, the batch and both
   refusals. The apply route's own inline copy is gone; its 404 sentence now ends "nothing to
   review" rather than "nothing to apply", because four acts share it.
5. **Two vitest cases changed rather than added**, both citing AC-F.4 in the diff: the group's
   select-all now ticks three rows (was two, excluding the conflict), and the row-checkbox test
   now asserts the conflict is ENABLED and the `unchanged` row is the disabled one. The shared
   component's "disables the conflict checkbox when selectableKinds is [new, change]" was renamed
   to say what it tests (a caller leaving `conflict` out) rather than naming the flyer surface,
   which no longer passes that list.

**Operational note:** a developer database that already ran migration 370 is STAMPED at it, so the
folded ALTERs do not re-run there. This worktree's shared dev database had the three columns
applied by hand with exactly the statements above. A fresh database, and production, get them from
the migration.

### 7d. The review page findings, after the F+G evidence run (S6)

The evidence run (section 6b) and the review that followed it left five findings on the review
page and three test gaps behind the routes. All eight are closed in one commit; nothing in the
contract moved except AC-F.1, which gains a stated consequence rather than a changed rule.

**Frontend.**

1. **Clearing the search left the list stranded** (6b step 8, the one defect the run found).
   `shown` is a depth into whatever list is on screen, and it survived a change of list: a depth
   reached inside a filter, carried back out of it, either painted every product in the batch at
   once or left the restored list capped with no `Show more` to ask for the rest, so groups became
   unreachable without reloading the page. Every search change now restarts the paging from the
   top, and the box carries its own clear button - one deterministic click back to the whole
   batch, which the tester's three repros had to do with a page reload.
2. **A dismissed row kept its tick.** The dismiss went to the server and the row left the batch,
   but its id stayed in the page's selection: the sticky bar counted a row that no longer exists
   and Apply sent an id the server answers `not_in_batch` for. Pruned once the delete resolves -
   a REFUSED dismissal leaves the row and its tick alone.
3. **A just-added row was never ticked.** The load-time seeding pass ticks every `new` row and
   does not run again for the batch, so a specification somebody typed a second ago was the one
   row Apply left out. The add now ticks the returned row - unless the value they typed is what
   the product already holds, which is not tickable at all.
4. **A multi-value proposal offered an edit that lost half of it.** `toDraft`/`fromDraft` carry
   ONE value, so opening the editor on `finish = ["rose_gold", "matt_black"]` showed the first and
   saving stored the first. The pencil is disabled for a proposal holding more than one value,
   with the reason on it ("Multi-value specifications are edited on the product page"); applying
   the row untouched still writes both. A list of one is not a list and still edits here.
5. **`conflict_not_confirmed` read as the wrong refusal.** "Not replaced" was written when a
   conflict could not be applied at all; since AC-F.1 a ticked conflict IS written, so the only
   row that comes back with this outcome is a key somebody tombstoned. It now reads "Removed by a
   person", which is what happened.

**Backend.**

6. **`proposal_id` (PATCH, DELETE) and `product_id` (`POST .../rows`) are `UUID`, not `str`.**
   They are UUID columns, so a malformed value went to the driver and came back a 500 - our fault
   for a request the caller got wrong. 422 at the edge now, naming the field; the service layer
   still takes the canonical string. The apply body already declared `list[UUID]`.
7. **Three test gaps closed, no behaviour changed by any of them:** AC-G.1's
   `flyer_spec_key_not_applicable` (400) had no test - a `bowl_count` (gated `Kitchen Sink`) added
   to a product whose DESCRIPTION reads Water Closet, which is what the gate needs, since a class
   inherited from the category deliberately gates nothing; a proposal id from another reading's
   batch, on both PATCH and DELETE, answering 404 `not_in_batch`; and the description-first half of
   AC-F.1, where a ticked `dim_height` conflict is written over the master's own derived value and
   stored as `flyer` with the printed words as evidence.

**The consequence of 7, stated rather than fixed (AC-F.1, BL-016).** `flyer` is an AUTHORED
source, which is the point - the reviewed value survives re-derivation. So the next `derive` that
reads the same description disagrees with it, and `merge_authored_over` raises
`human_override_conflict` for that key, putting the row in `needs_review`. That is D8 doing its
job: the paper and the master disagree and a person is meant to see it. But bulk-ticking forty
dimension conflicts parks forty open exceptions nobody asked for, and whether that should be
quieter (suppressed where the authored value came from a reviewed flyer proposal, or resolved on
apply) is the captain's call. Nothing here suppresses it; logged as **BL-016**.

**Counts at the S5 hand-off:** pytest 163 green over
`test_dealer_kit_flyer_spec_proposal_routes` (50), `test_product_spec_flyer_ingest_service`,
`test_product_spec_flyer_classify`, `test_product_spec_flyer_authored_source`,
`test_product_spec_write`, `test_product_spec_batch_apply_route` and
`test_dealer_kit_flyer_dimensions`; vitest 212 green over 13 files across
`flyer-spec-proposals`, `components/spec-proposals` and `dealer-kit/flyer-readings`.
`alembic heads` is one head, `370_flyer_spec_proposals`.

**Counts after the S6 follow-up above:** pytest 170 green over the same seven files
(`test_dealer_kit_flyer_spec_proposal_routes` 57, `test_product_spec_flyer_ingest_service` 19,
and 94 across the other five); vitest 219 green over the same 13 files. No migration, so
`alembic heads` is unchanged at the single head `370_flyer_spec_proposals`.

## 6c. Re-walk after the fixes (S7, `dfc6a1bb`)

**Completed 2026-08-17, own agent stack** (BE `:8040`, worker on `WORKER_QUEUES=flyer_read`
against `REDIS_URL=redis://localhost:6379/5`, FE `npm run dev` on `:3040` with
`NEXT_PUBLIC_API_URL=http://localhost:8040`; `:3000`/`:8000` untouched, belong to other lanes),
against the shared dev Postgres, via `npx -y agent-browser@0.27.0 --session spec-flyer-rewalk`.
Scope: the five findings fixed in `dfc6a1bb` (search-clear, dismiss-prunes-tick,
add-ticks-unless-already-stored, multi-value pencil disabled) plus a clean 375x812 pass. Login
used `E2E_EMAIL`/`E2E_PASSWORD` from `sorento_crm_frontend/.env.local` (values never echoed).
`get url` was checked before trusting reads. Navigation started from `/` via the sidebar, per
policy - the Product Management accordion needed a JS `.click()` dispatch via `eval` rather than
a ref-based `click` (same tooling friction section 6b already documented; the accordion and its
links work correctly once actually triggered). All PIDs started here (backend, worker, frontend)
were killed at the end; the browser session was closed with a plain `close`, never `close --all`.

### Walk

1. **Search.** Opened `flyer_sample.pdf`'s review page (list showed `0 new, 14 change, 16
   conflict` - `Propose again` was not needed, plenty of pending rows). Baseline: 25 of 34
   product groups, `Show more products (9 left)`. Screenshot: `rw-01-review-page-baseline.png`.
   - Typed `SRTJC80` -> filtered to exactly the 6 matching groups
     (`SRTJC8018`/`8028`/`8030`/`8037`/`8041`/`8066`), no `Show more` (all fit). Screenshot:
     `rw-02-review-page-search-filtered.png`. Cleared via the new **x** ("Clear the search")
     button -> back to the full 25-group first page **and** `Show more products (9 left)`
     restored. Screenshot: `rw-03-review-page-search-cleared-x-button.png`. This is the exact
     bug (`shown` depth carried across a list change) - confirmed fixed.
   - Typed `SRT` (33 of 34 groups match) -> 25 shown, `Show more products (8 left)`. Clicked
     `Show more` -> all 33 SRT-matching groups rendered, `Show more` gone. Screenshot:
     `rw-04-review-page-search-showmore-expanded.png`. Cleared via the **x** button -> back to
     25 groups + `Show more products (9 left)` for the FULL unfiltered 34, not the 33-match
     count - confirms paging restarts from the top on every search change rather than being
     stranded inside the old filtered depth. Screenshot:
     `rw-05-review-page-search-cleared-after-showmore.png`.
   - Typed `SRTJC80` again (6 matches), then cleared via keyboard select-all (`End`,
     `Shift+Home`) + `Delete` inside the input instead of the x button -> same correct outcome:
     25 groups, `Show more products (9 left)`, input empty. Screenshot:
     `rw-06-review-page-search-cleared-select-all-delete.png`. Console/errors clean throughout.
2. **Dismiss a ticked row.** Ticked `SRTJC8037`'s `Height` (`conflict`, `600 mm` vs stored
   `590 mm`) -> footer `Apply 1 selected`. Screenshot: `rw-07-review-page-one-row-ticked.png`.
   Clicked `Dismiss Height` -> `AlertDialog` **"Dismiss this proposal? It will not be applied.
   This action cannot be undone."** naming the row (`Height 600 mm`). Screenshot:
   `rw-08-dismiss-confirm-dialog.png`. Confirmed -> `DELETE
   .../spec-proposals/{proposal_id}` **200**, followed by a `GET .../spec-proposals` refresh.
   Sticky bar dropped to **`Apply 0 selected`** and the row was gone from the DOM - confirms the
   tick was pruned, not just the row. Ticked two remaining rows (`SRTWC287-RL` `Trap`
   change, `SRTWC7614-RL` `Length` conflict) -> `Apply 2 selected`, clicked Apply -> confirm
   dialog **"Replace 2 master values, 1 of them set by a person?"** (no mention of the dismissed
   row), confirmed -> `POST .../spec-proposals/apply` **200**, result text contained no
   `not_in_batch` anywhere on the page (checked via `document.body.innerText.includes(...)`) and
   did show the success sentence ("... written to the product master"). Screenshot:
   `rw-09-apply-after-dismiss-no-not-in-batch.png`. Console/errors clean.
3. **Add specification.** `FG-CW13` -> `Add specification` -> key picker excluded
   `Capacity (oz)`/`Type` (already on the product); picked `Finish or colour` -> closed
   vocabulary value picker; picked **`Black`**, the value already stored on this product from an
   earlier evidence run. Screenshot: `rw-10-add-specification-value-picked.png`. `Add` ->
   `POST .../spec-proposals/rows` **201**. New row: `Finish or colour Black edited Already
   stored`, checkbox `checked=false` **and disabled** - arrives unticked, per the fix (a value
   equal to what the product already holds is never selectable). Screenshot:
   `rw-11-add-specification-equal-to-stored-unticked.png`. Second case for contrast:
   `SRTMRL707` -> `Add specification` -> `Material` -> `Nanograin` (not previously stored) ->
   `POST .../rows` **201** -> row `Material Nanograin edited New`, checkbox `checked=true`, not
   disabled - a genuinely new row arrives ticked. Screenshot:
   `rw-12-add-specification-new-value-ticked.png`. Console/errors clean both times.
4. **Multi-value row, pencil disabled.** `flyer_sample.pdf` carries no proposal whose own
   `value` is a multi-item array at the time of this walk (its one multi-value-looking row,
   `FG-CW13`... `SRTWC8066-S-MBL Finish or colour "Matte black, Black"`, has that shape on the
   STORED side only, and is `kind=unchanged` with no edit action at all - not the case this fix
   targets). Cross-checked via `psql` against `product_spec_flyer_proposals` for a
   `jsonb_array_length(value) > 1` row with `kind IN ('new','change','conflict')`, which surfaced
   several in the *other* batch (`_SORENTO A3 FLYER 2025-2026_compressed.pdf`,
   `0c32665c-e3e4-45d8-bc93-0536bcaca773`). Navigated to it via the list page (click through, not
   a deep URL) and searched `SRTWB1413-BL`: **`Finish or colour` `Rose gold, Black` `Conflicts
   with your value Black`** - a `conflict` row whose own proposed value is the 2-item array
   `["rose_gold", "black"]`. Its `Edit Finish or colour` button has `disabled=true`; the hover
   hint is a native `title="Multi-value specifications are edited on the product page"` on the
   wrapping `<span>` (not the button itself - a disabled button blocks pointer events, so a
   tooltip anchored on it would never open, which the diff's own comment calls out). The row's
   **checkbox stayed enabled** (`disabled=false`) - applying the row untouched still writes both
   values, only the in-place edit is blocked. Screenshot: `rw-13-multivalue-pencil-disabled.png`.
   Console/errors clean. **Deviation from the brief, recorded honestly:** the walk needed to
   leave the named `flyer_sample.pdf` batch to find a live example, because that batch does not
   currently carry one; the fix itself was exercised against a real multi-value row from the
   other batch rather than skipped.
5. **375x812 screenshot.** Returned to `flyer_sample.pdf`'s review page (list page click, not a
   deep URL), `set viewport 375 812`. Renders cleanly - header, counts sentence, search box, the
   `FG-CW13` group with its one remaining row, sticky `Apply 1 selected` bar all visible with no
   horizontal overflow (the `1 ticked` reflects the `Material`/`Nanograin` row added to this same
   batch in step 3, still ticked). Screenshot: `rw-14-review-page-375x812.png`. Console/errors
   clean.

### Network calls asserted

`network requests --filter /api/v1/dealer-kit` and `--filter /spec-proposals` checked after
every state-changing step:

- `DELETE /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/{proposal_id}` -> **200**
  (step 2 dismiss), followed by a `GET .../spec-proposals` refresh
- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/apply` -> **200** (step 2 apply of
  the two remaining ticked rows)
- `POST /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals/rows` -> **201** (step 3, x2: the
  already-stored `Black` add and the new `Nanograin` add)
- `GET /api/v1/dealer-kit/flyer-readings/{id}/spec-proposals` -> **200** (repeated - every
  search/dismiss/add/apply refresh and every page load)

### Console / errors

Checked via `console` and `errors` after every state-changing step across all five points
(search x-clear, search-showmore-then-clear, keyboard-clear, tick, dismiss-confirm,
dismiss-result, apply-result, add-equal-to-stored, add-new-value, the cross-batch multi-value
lookup, the 375x812 pass). Clean throughout - no warnings or uncaught errors surfaced anywhere in
this run.

### Evidence files

`documentation/plans/master-data/evidence/flyer-spec-ingestion/`, all prefixed `rw-`:

`rw-01-review-page-baseline.png`, `rw-02-review-page-search-filtered.png`,
`rw-03-review-page-search-cleared-x-button.png`,
`rw-04-review-page-search-showmore-expanded.png`,
`rw-05-review-page-search-cleared-after-showmore.png`,
`rw-06-review-page-search-cleared-select-all-delete.png`,
`rw-07-review-page-one-row-ticked.png`, `rw-08-dismiss-confirm-dialog.png`,
`rw-09-apply-after-dismiss-no-not-in-batch.png`,
`rw-10-add-specification-value-picked.png`,
`rw-11-add-specification-equal-to-stored-unticked.png`,
`rw-12-add-specification-new-value-ticked.png`, `rw-13-multivalue-pencil-disabled.png`,
`rw-14-review-page-375x812.png`.

### Outcome

**All five re-walk points pass.**

1. **Search clear restores the list** (both via the new x button and via keyboard
   select-all+delete), in both the no-show-more and the show-more-then-clear cases. This was the
   one defect the F+G run found and left open; confirmed fixed.
2. **Dismissing a ticked row drops the sticky count and prunes the tick** - the subsequent Apply
   of the remaining ticked rows returned no `not_in_batch` refusal anywhere in the rendered
   result.
3. **Add specification: a new value arrives ticked; a value equal to the stored one arrives
   "Already stored" and unticked** (checkbox disabled) - both halves demonstrated on two
   different products in the same batch.
4. **Multi-value proposals disable the pencil with the exact hover hint**
   (`"Multi-value specifications are edited on the product page"`) while leaving the row's
   checkbox tickable; no live example existed in the `flyer_sample.pdf` batch itself, so this
   point was verified against a genuine multi-value row in the other flyer batch instead of being
   skipped - recorded as a deviation from the brief, not a gap in verification.
5. **Console and `errors` were clean at every step**, including the 375x812 viewport pass with no
   horizontal overflow.

No new defects found. No backlog entries added.
