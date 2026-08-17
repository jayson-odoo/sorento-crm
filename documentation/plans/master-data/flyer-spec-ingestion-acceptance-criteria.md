# UAC - Flyer / catalogue ingestion into product specifications

> Given/When/Then contract for the bulk flyer-to-spec slice ("PR 5" of the spec authoring
> milestone). Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.
> Plan: `PLAN-flyer-spec-ingestion.md`. Parent contract: `spec-authoring-verification-acceptance-criteria.md`
> (AC-B.18 names this slice; AC-F.7 reserves the `AUTHORED_SOURCES` membership flip for it).

**Slug:** `flyer-spec-ingestion` · **Domain:** master-data · **Milestone:** 1, slice after PRs 1-4
**Classification:** CORE, schema `public`, normal FKs (a cross-schema FK onto
`dealer_kit.flyer_reading`, which the dealer kit already owns).
**Status:** DRAFT - written 2026-08-17 from the captain's decisions and the design report
`flyer-spec-ingestion/report.md` §5. Not captain-reviewed; build proceeds under it (captain
order 2026-08-17: "we need it - upload flyer / catalogue then read the spec"; the brief says
"do NOT wait for the captain").

## Scope

One upload, one background proposal pass, one review screen, one apply route.

- The dealer-kit flyer upload and its background read (PR #184) are the ONLY upload. No second
  reader (report §5.4 "one upload, two consumers").
- After a reading is `done`, a person presses **Propose specs from this flyer**. A background pass
  runs `propose_from_text` (PR 4, `product_spec_derivation.propose_from_text`) once per matched
  product and **stores** the proposals as a batch, each row classified against what the product
  holds today.
- A review screen lists the batch **grouped by product**, per-row state
  `new` / `change` / `conflict` / `unchanged` / `suppressed`, select-all per product, `new` ticked
  by default, `change` unticked, the other three not tickable.
- Apply writes the ticked rows through PR 1's choke point (`apply_spec_values`) with
  **`source='flyer'`**, which this slice adds to `AUTHORED_SOURCES`. Every refusal is reported by
  row with a reason.
- A Master Data list of proposal batches, so a merchandiser finds a batch without going through
  the dealer kit.

**Not in scope:** a vision read of the flyer artwork (report §4.4); a second per-key grouping mode
(the captain chose per-product); the verification-reset preview count (PR 3's verification model
is not on main yet - see AC-E.4); re-deriving anything from `ProductFlyerText` (PR 4 retires it).

## Locked decisions (captain / brief - do not reopen)

| # | Decision |
|---|---|
| L1 | **Option A** (report §5.2): the flyer is a proposal producer, never a derivation input. Accepted rows are authored values. |
| L2 | **`source='flyer'` for an accepted proposal, never `human`** (report §5.3, parent AC-B.18). `flyer` joins `AUTHORED_SOURCES` in THIS slice, after promote migration 367 (parent AC-F.7). Same conflict-winning and re-derivation-surviving mechanics as `human`; the badge still reads "Flyer". |
| L3 | **Reuse, do not rebuild:** `POST /dealer-kit/flyer-readings` + `app/tasks/flyer_read_tasks.read_flyer` (upload + read); `propose_from_text` (extraction); the kind classifier in `product_spec_extract.py` (lifted, not copied); `components/spec-proposals/SpecProposalReview` (review rows); `apply_spec_values` (write); `_value_for_registry` (registry validation, lifted to a service module so two routes share it). |
| L4 | **Proposals are stored** (captain brief: "stores proposals"; a listing of batches needs rows). The stored `kind` is a snapshot; apply re-classifies against the live row and refuses what no longer holds. |
| L5 | **Grouped by product** with select-all per product (captain brief). Report §5.4's per-key grouping is not built. |
| L6 | **`change` unticked by default**, so a default apply is gap-filling (report §5.5). `new` ticked. `conflict` (authored value or tombstone disagrees), `unchanged`, `suppressed` are not tickable in bulk; the per-product Specifications tab is the path for those. |
| L7 | **Bulk never overwrites an authored value or a tombstone** (report §5.5, D8). Refused as `conflict_not_confirmed`, and derivation's `human_override_conflict` exception is what flags the disagreement. |
| L8 | **The apply request names proposal ids, never values** (report §5.4, `dimension_apply_service` security model). The values come from the stored proposal, which came from the reading. |
| L9 | **Permissions:** every new route requires `dealer_kit.page.view` AND `master_data.products.edit`, declared in that order, no API-key variant - the precedent of `apply_flyer_dimensions`. |
| L10 | **`unchanged` is never written**: re-applying the same flyer produces zero writes, zero fan-outs and zero verification resets (report §5.6.3, §5.7). |
| L11 | Simplest thing that works: two tables (batch, proposal), one RQ task on the existing `flyer_read` queue, four routes, one review page, one list page, one section on the reading page. No new queue, service class, config knob or permission. |

**Amended 2026-08-17 (captain, hands-on on the review page - supersedes L6/L7 in part):**
`conflict` rows (an authored value or a description-first key disagrees) are **tickable in
bulk**, unticked by default, exactly like `change`; the tick plus the confirm dialog naming the
overwrite count IS the confirmation, and apply writes them. Only `unchanged` ("Already stored")
and `suppressed` (tombstoned) rows stay un-tickable. And a proposal's **value is editable in
place** on the review page before applying - the widget follows the key's registry type
(dropdown for a closed vocabulary, yes/no for boolean, number for numeric, text otherwise); the
edit is stored on the proposal row server-side and validated against the registry, so the apply
request still names ids only (L8 stands).

## Journey

**Actor:** a merchandiser holding `master_data.products.edit` (and `dealer_kit.page.view`, which
the same roles hold). **Arrives from:** marketing released the new A3 flyer; the spec table does
not know what it says.

**What the system already knows:** every code printed on the flyer, which are products, what each
card says, what each product holds for every spec key and who set it, which keys a person has
tombstoned, and which keys apply to the product's class. None of it is asked for.

1. **Upload once.** Sidebar `Dealer Kit -> Flyers -> Read a flyer`, choose the PDF. The row appears
   as `Processing` and flips to `Done` on its own (PR #184, unchanged). The reading page shows the
   match report exactly as today.
2. **One press.** A new **Specifications** section sits beside Dimensions on the reading page. It
   holds one button, `Propose specs from this flyer` (hidden without `master_data.products.edit`).
   Pressing it shows `Proposing...`; when finished the section reads *"This flyer states N
   specification values across P products: A new, B change what the master says, C conflict with
   a value a person set, D unchanged, E suppressed"* with a `Review proposals` link. A read that
   is not `Done` yet has the button disabled with the reason.
3. **Review, grouped by product.** `Master Data -> Product Management -> Flyer Spec Proposals`
   lists every batch (flyer name, read date, proposed date, status, counts, applied). Opening one
   shows the products in flyer order, each with its code, name, a select-all for that product, and
   its proposal rows: key, proposed value, the printed words it was read from, what the product
   holds today and who set it, and the state pill. `new` rows arrive ticked; `change` unticked;
   `conflict` / `unchanged` / `suppressed` cannot be ticked. A sticky footer counts the ticked rows.
4. **Apply.** `Apply N selected`. If any ticked row is a `change`, an `AlertDialog` names how many
   master values will be replaced before the write. The result names every row: applied, or
   refused and why. Nothing else moves: the ticked rows are written as `Flyer` values with the
   printed words as evidence, and the batch remembers what was applied and by whom.
5. **Leave with** the specs updated and badged `Flyer`, evidence on every value, the batch marked
   applied in the list, and (once PR 3 ships) a stated count of verifications the change reset.
   Every other stakeholder learns through the spec table itself; no notification is sent.

## Acceptance criteria

### A - Propose (Phase 2 backend; journey steps 1-2)

- **AC-A.1** `[BE]` GIVEN a `done` flyer reading WHEN `POST /dealer-kit/flyer-readings/{id}/spec-proposals`
  is called by a user holding both permissions THEN a `product_spec_flyer_batches` row exists for
  the reading in status `proposing`, an RQ job is enqueued on the `flyer_read` queue, and the
  response is **202** with the batch summary. A reading that is `processing` or `failed` is refused
  **409 `FLYER_NOT_READ_YET`** with the same words `seed` and `dimensions/apply` use.
- **AC-A.2** `[BE]` GIVEN the job runs WHEN it finishes THEN one `product_spec_flyer_proposals` row
  exists per (matched product, spec key) that `propose_from_text(card text, code)` yields, with
  `value`, `unit` (from the registry row), `evidence` (the printed words), `kind`, and a snapshot
  of the stored value / unit / source at propose time; the batch flips to `proposed` with
  `product_count`, `proposal_count` and per-kind counts filled and `finished_at` stamped. Cards
  whose code is `unmatched` yield nothing. A `not_promoted` code DOES yield proposals: it is a
  subset of `matched` (a real product the linked promotion happens not to carry), and whether
  marketing put a product in a promotion says nothing about what its card prints. Corrected
  2026-08-17 in review - the first draft of this line said `not_promoted` yields nothing, which
  the code never did and should not. Hits with `origin == "code"` are not
  proposals (PR 4 rule: read off the code, not the paper). Keys outside the product's class scope
  are not proposals (the same `_apply_scope` gate).
- **AC-A.3** `[BE]` GIVEN the classifier WHEN a proposal is compared to the stored entry THEN the
  kind is decided by ONE function shared with `extract_spec_proposals` (lifted out of it, not
  copied): tombstoned key -> `suppressed`; equal after `_canonical_entry` -> `unchanged`; stored
  source in `AUTHORED_SOURCES` -> `conflict`; no stored entry -> `new`; key in
  `_DESCRIPTION_FIRST_KEYS` -> `conflict`; else `change`. `extract_spec_proposals` keeps its
  present behaviour byte-for-byte (its callers still see `conflict` for a tombstone and never see
  `unchanged` rows).
- **AC-A.4** `[BE]` GIVEN the job raises anywhere WHEN it exits THEN the batch is `failed` with
  `error_message` set, nothing is left `proposing`, and the job returns rather than raises (the
  `read_flyer` shape). A batch whose reading vanished mid-job is left alone (cascade removes it).
- **AC-A.5** `[BE]` GIVEN a reading that already has a batch WHEN propose is called again THEN a
  batch in `proposing` is refused **409**; otherwise the existing proposals are deleted, the batch
  reset to `proposing`, and the job re-runs against the master as it is now. Applied history lives
  in the spec provenance, not in the deleted rows.
- **AC-A.6** `[BE]` GIVEN the same flyer bytes uploaded twice WHEN each is proposed THEN each
  reading gets its own batch; nothing about the propose pass depends on `sha256`.
- **AC-A.7** `[BE]` GIVEN a caller lacking `dealer_kit.page.view` OR `master_data.products.edit`
  WHEN any of the four routes is called THEN **403**, and the message names the missing
  permission (`page.view` first). Unauthenticated -> 401. The routes are under the `dealer_kit`
  module guard.

### B - Read the batch (Phase 2 backend; journey steps 2-3)

- **AC-B.1** `[BE]` GIVEN a batch WHEN `GET /dealer-kit/flyer-readings/{id}/spec-proposals` is
  called THEN it returns the batch summary (status, error, counts, `applied_at`, `applied_by_name`)
  and, when `proposed`, every proposal grouped by product in flyer page order:
  `{product_id, product_code, product_name, pages, proposals: [{id, spec_key, label, data_type,
  value, unit, evidence, kind, stored_value, stored_unit, stored_source, outcome, applied_at}]}`.
  A reading with no batch returns the summary with `status: "none"` and no groups. Never 404 for
  "no batch yet".
- **AC-B.2** `[BE]` GIVEN `GET /dealer-kit/flyer-readings/spec-proposal-batches` WHEN called THEN
  it lists every batch the caller's company scope can see, newest first, each with the reading's
  filename, `created_at`, `finished_at`, status, counts and `applied_at`. Declared before the
  `{reading_id}` routes so the static path wins.
- **AC-B.3** `[BE]` GIVEN a proposal row WHEN it is serialised THEN no UUID reaches the UI except
  `id` (needed for the apply payload) and `product_id` (needed for the product link); the product
  is shown by code and name.

### C - Apply (Phase 2 backend; journey step 4)

- **AC-C.1** `[BE]` GIVEN `POST /dealer-kit/flyer-readings/{id}/spec-proposals/apply` with
  `{proposal_ids: [...]}` WHEN it runs THEN it accepts ids only (a body carrying values is 422),
  refuses more than `MAX_ROWS = 5000` ids with a readable message, ignores ids not in this batch
  (refused `not_in_batch`), and returns **200** with `applied: [{proposal_id, product_code,
  spec_key, value}]` and `refused: [{proposal_id, product_code, spec_key, reason, message}]`.
- **AC-C.2** `[BE]` GIVEN a selected proposal WHEN it is applied THEN it is re-classified against
  the LIVE spec row first (AC-A.3's function): `unchanged` -> refused `already_matches`, no write;
  `suppressed` -> refused `conflict_not_confirmed`, no write; `new` / `change` / `conflict` ->
  written (conflict per AC-F.1, captain amendment 2026-08-17). Kinds are re-checked at apply time because the master may have moved since propose.
- **AC-C.3** `[BE]` GIVEN the rows to write for one product WHEN they are written THEN it is ONE
  `apply_spec_values(db, product_code, entries, actor=user, commit=False)` call per product (parent
  AC-B.9), each entry `{"spec_key", "op": "set", "value": _value_for_registry(row, value),
  "unit": row.unit or None, "source": "flyer", "evidence": "flyer <filename>: <printed words>"}`,
  and one commit for the whole request. `_value_for_registry` is imported from the service module
  it is lifted into (`app/services/product_spec_registry.py`), and the PR 4 batch route imports it
  from the same place - one helper, two callers.
- **AC-C.4** `[BE]` GIVEN a proposal that `apply_spec_values` rejects (400 `product_spec_bad_value`,
  404 `product_not_found`) WHEN the batch runs THEN that PRODUCT's rows are refused with the
  message and the other products still apply; the response is still 200.
- **AC-C.5** `[BE]` GIVEN an applied proposal WHEN the request commits THEN its row carries
  `outcome='applied'`, `applied_at`, `applied_by`; a refused one carries `outcome=<reason>`; the
  batch carries `applied_at` / `applied_by` of the latest apply and `applied_count`.
- **AC-C.6** `[BE]` GIVEN the idempotency test WHEN a batch is applied, then re-proposed and
  applied again with the same selection THEN the second apply writes zero rows, runs zero fan-outs
  (no `product_specifications.updated_at` moves), and returns every row `already_matches`.
- **AC-C.7** `[BE]` GIVEN `AUTHORED_SOURCES` WHEN this slice lands THEN it is
  `frozenset({"human", "supplier", "flyer"})`; a `source='flyer'` entry passes `_prepare`;
  `merge_authored_over` keeps a flyer value over derivation and raises `human_override_conflict`
  when derivation disagrees; `_is_authored` / `authored_keys` / `_status_for` treat it as authored
  (`status='authored'`); the search boost branch still reads `flyer_source_boost` for it (parent
  C3, AC-F.10). The FE `SpecSourceBadge` `AUTHORED_SOURCES` set gains `flyer` and keeps the
  "Flyer" label. Existing tests that assert `flyer` is NOT authored are updated with the reason
  in the diff.
- **AC-C.8** `[T]` Every new pytest runs on Postgres only via `tests/_pg_fixture.py`, seeds its
  own product / category / registry / reading chain with a marker prefix, and cleans children
  first. The job runs inline through `tests/_flyer_read.py`'s pattern (patch the enqueue seam,
  run the task with `_db=db`).

### D - Frontend (Phase 1 mock, then Phase 2 wiring; journey steps 2-5)

- **AC-D.1** `[FE]` GIVEN the reading page WHEN it renders THEN a **Specifications** section is
  always present beside Dimensions (never hidden): status `none` shows the button (or, without
  `master_data.products.edit`, the empty copy "No spec proposals yet" and no button); `proposing`
  shows a spinner and polls every 3 s like the reading itself; `proposed` shows the counts sentence
  and a `Review proposals` link to `/master-data-management/flyer-spec-proposals/{readingId}` plus
  a `Propose again` action; `failed` shows the error and `Try again`. A reading not yet `done`
  shows the button disabled with "Read the flyer first".
- **AC-D.2** `[FE]` GIVEN the review page WHEN it renders a `proposed` batch THEN products appear
  in flyer order, each a `Card` with code, name, page numbers, a per-product select-all checkbox,
  and the shared `SpecProposalReview` for its rows. The shared component gains the two new kinds
  (`unchanged`, `suppressed`) as **data**: their rows are not selectable and carry their own pill,
  and select-all skips them. It stays product-blind and imports no service.
- **AC-D.3** `[FE]` GIVEN the selection WHEN the page loads THEN every `new` row is ticked and
  nothing else; per-product select-all ticks all `new` + `change` rows of that product; there is
  no cross-product select-all (D12). The sticky footer reads `Apply N selected` and is disabled at
  0. Selection is held in page state keyed by proposal id.
- **AC-D.4** `[FE]` GIVEN at least one ticked `change` row WHEN Apply is pressed THEN an
  `AlertDialog` reads "Replace K master values?" with the count before the request; with only
  `new` rows ticked it applies directly. After apply the result table lists applied and refused
  rows with reasons, the batch summary refreshes, and applied rows render disabled with an
  `Applied` mark.
- **AC-D.5** `[FE]` GIVEN the review page WHEN the batch is `none` / `proposing` / `failed` /
  `proposed` with zero rows THEN each state renders explicitly: `none` -> "This flyer has no spec
  proposals yet" with a `Propose specs` button; `proposing` -> spinner + polling; `failed` -> the
  error + `Try again`; zero rows -> "The flyer stated nothing the master does not already hold".
- **AC-D.6** `[FE]` GIVEN the sidebar WHEN it renders for a `master_data.products.edit` holder
  THEN `Product Management -> Flyer Spec Proposals` exists in BOTH `MENU_SIDEBAR` and
  `MENU_SIDEBAR_COMPACT` (the two menus that carry this application's Product Management group).
  Corrected 2026-08-17 in review: this line originally named `MENU_MEGA`, which carries no
  Master Data group at all - it is the Metronic demo mega menu - so an entry there would have
  had nowhere to sit. Gated on `master_data.products.edit`, leading to a `DataGrid` list of batches (flyer, read on,
  proposed on, status pill, products, proposals, new/change/conflict counts, applied on) with row
  click to the review page. Fixed layout, explicit `size`, `truncate` + `title`, empty state
  "No flyer has been proposed yet - read a flyer in Dealer Kit and press Propose specs".
- **AC-D.7** `[FE]` GIVEN the layering rule WHEN the code lands THEN
  UI -> `useFlyerSpecProposals*` hooks -> `services/flyerSpecProposalService.ts` -> `apiFetch`, the
  contract block at the top of the service, `extractApiError` for errors, `useHasPermission` for
  the gates. Phase 1 ships the pages against `__mocks__` fixtures (a 3-product x mixed-kind batch,
  an empty batch, a failed batch, a proposing batch); Phase 2 swaps the mock at the service
  boundary and deletes the fixtures unless the tests use them.
- **AC-D.8** `[FE]` GIVEN vitest WHEN Phase 2 lands THEN component tests cover the reading-page
  section in all four statuses, the review page in `proposed` / empty / failed / proposing, the
  default selection rule (AC-D.3), the change-confirmation dialog (AC-D.4), the two new kinds in
  `SpecProposalReview`, and the list page with rows and empty; hook tests cover the polling rule
  and the apply invalidation.

### E - Verification interaction and evidence

- **AC-E.1** `[E2E]` GIVEN a user WHEN they navigate **by sidebar clicks from `/`** to
  `Dealer Kit -> Flyers`, open a `Done` reading of the committed fixture
  (`tests/fixtures/dealer_kit/flyer_sample.pdf`), press `Propose specs from this flyer`, wait for
  the counts, click `Review proposals`, untick one `new` row, tick one `change` row, apply and
  confirm, THEN the result lists the applied rows, the product's Specifications tab shows the
  value badged `Flyer` with the printed words as evidence, and a second propose + apply of the
  same selection returns all `already_matches`. Recorded as an agent-browser evidence run in the
  plan (no new Playwright spec, per CLAUDE.md), asserting the calls were `POST .../spec-proposals`,
  `GET .../spec-proposals`, `POST .../spec-proposals/apply`. Clean console at **375px and 1280px**.
- **AC-E.2** `[E2E]` GIVEN the same walk WHEN it reaches Master Data THEN
  `Product Management -> Flyer Spec Proposals` lists the batch with status `Applied` and opens the
  same review page.
- **AC-E.3** `[BE]` GIVEN a bundle card (one card naming another code-shaped token, report §3.5)
  WHEN it is proposed THEN it is still proposed (the reviewer sees the printed words and unticks
  what belongs to the neighbour); nothing in this slice widens the importer's guard - that
  importer is dead code PR 4 retires. Recorded as an accepted limitation, not built.
- **AC-E.4** `[BE]` GIVEN PR 3's verification model is not on main WHEN this slice ships THEN the
  verification reset is owed to `apply_spec_values` (the choke point PR 3 instruments), NOT to
  this slice; the "applying N will reset verification on M products" preview (report §5.6.2) is
  logged in `documentation/backlogs/backlog.md` as a follow-up gated on PR 3, and the plan says
  so. AC-C.6's zero-write re-apply is what guarantees zero resets on re-ingest today.

### F - Conflict apply and inline edit (captain amendment 2026-08-17)

- **AC-F.1** `[BE]` GIVEN a ticked `conflict` or `change` proposal WHEN apply runs THEN it is
  WRITTEN (source `flyer`, same evidence rules); only `unchanged` (`already_matches`) and
  `suppressed` (`conflict_not_confirmed`) refuse. Live re-classification still runs: a row that
  became `unchanged` since propose still refuses with no write (AC-C.6 idempotency holds).
- **AC-F.2** `[BE]` GIVEN `PATCH /dealer-kit/flyer-readings/{id}/spec-proposals/{proposal_id}`
  with `{value}` WHEN called by a holder of both permissions THEN the value is validated via
  `value_for_registry`, stored on the proposal row with `edited_at` / `edited_by`, the row's
  `kind` recomputed against the live spec row, and the batch's per-kind counts refreshed.
  Refused: 409 when the batch is not `proposed`, 409 when the row is already `applied`,
  400 with the registry's own words for a bad value. The GET returns the edited value and an
  `edited` marker so the screen can show it.
- **AC-F.3** `[FE]` GIVEN a pending proposal row WHEN the user activates its edit affordance
  THEN the Value cell swaps in place to the registry-typed input (closed vocabulary -> select of
  allowed values; boolean -> yes/no select; numeric -> number input; else text), save PATCHes and
  the row re-renders with the new value, kind pill and an "edited" mark; cancel restores. Applied
  and unchanged/suppressed rows offer no edit.
- **AC-F.4** `[FE]` GIVEN the selection rules WHEN the page loads THEN `new` rows are ticked;
  `change` AND `conflict` are tickable (unticked); per-product select-all ticks every tickable
  row of that product; the confirm dialog copy names both counts ("Replace K master values, D of
  them set by a person?") whenever any change/conflict is ticked.
- **AC-F.5** `[BE]` GIVEN the GET payload WHEN a key has a closed vocabulary THEN each proposal
  row carries `allowed_values` (merged registry vocabulary) so the edit widget needs no second
  call.

### G - Review page is the whole act: add, dismiss, search (captain amendment 2026-08-17b)

- **AC-G.1** `[BE]` GIVEN `POST /dealer-kit/flyer-readings/{id}/spec-proposals/rows` with
  `{product_id, spec_key, value}` WHEN the batch is `proposed`, the product is in the batch, the
  key is in the registry and applicable to the product's class, and no row for
  (product, spec_key) exists in the batch THEN a proposal row is created with `kind` computed
  live, `origin='manual'`, `edited_by` stamped, value validated via `value_for_registry`;
  counts refresh. Refusals: 409 not proposed, 404 unknown key / product not in batch,
  400 bad value, 409 duplicate row ("the flyer already proposed this - edit that row").
- **AC-G.2** `[BE]` GIVEN apply THEN a `manual` row writes with **`source='human'`** and
  evidence `"set during flyer review"` (a person typed it; a machine read stays `flyer`).
  All other apply mechanics identical.
- **AC-G.3** `[BE]` GIVEN `DELETE /dealer-kit/flyer-readings/{id}/spec-proposals/{proposal_id}`
  WHEN the row is not `applied` and the batch is `proposed` THEN the row is hard-deleted and
  counts refresh; 409 otherwise. Same permission pair.
- **AC-G.4** `[FE]` GIVEN each product group WHEN it renders pending rows THEN it offers "Add
  specification" (key picker limited to applicable registry keys not already in the group,
  then the registry-typed value input) and per-row "Dismiss" behind a confirm dialog
  ("Dismiss this proposal? It will not be applied."). Applied rows offer neither.
- **AC-G.5** `[FE]` GIVEN the review page WHEN it holds more than one product THEN a search
  input filters product groups by code/name and by spec key label, client-side, keeping
  selection state for hidden rows intact.
- **AC-G.6** `[T]` The verification list (spec PR 3) is a DIFFERENT surface and stays out of
  scope; recorded so the question is answered in the contract.

## Test seams (agree before Phase 2 code)

- **pytest:** classifier lift (AC-A.3, byte-identical `extract_spec_proposals`); job happy path +
  failure path inline through the enqueue seam (AC-A.2, A.4); the four routes: happy, 401, 403 for
  each missing permission, 409 not read, 409 proposing (AC-A.1, A.5, A.7); apply outcomes per kind
  incl. live re-classification (AC-C.2), one call per product (AC-C.3, spy on
  `apply_spec_values`), partial failure (AC-C.4), stamps (AC-C.5), the idempotent re-apply
  (AC-C.6), the `AUTHORED_SOURCES` flip and its consequences (AC-C.7); ids-only body (AC-C.1).
- **vitest:** AC-D.8.
- **agent-browser evidence run:** AC-E.1, AC-E.2, written into the plan.
