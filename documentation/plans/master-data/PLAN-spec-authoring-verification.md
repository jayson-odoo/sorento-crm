# PLAN - Spec Authoring and Verification (milestone 1)

**Slug:** `spec-authoring-verification` · **Domain:** master-data · **Milestone:** 1 of 2
**UAC:** `spec-authoring-verification-acceptance-criteria.md` (the contract - this plan fulfils it)
**Classification:** CORE, schema `public`, normal FKs
**Status:** ACTIVE - reviewed with the captain 2026-08-14; **all open decisions settled** (list
not workbench, per-row and bulk Verify/Unverify, manual unverify, fix-the-value exception
handling, shared `DataGrid` for the spec table, server-side duplicate guards, cross-page
select-all off). Amended 2026-08-14: PR 4 lifts the flyer text pass into a pure
`propose_from_text` instead of deleting it, ahead of a bulk flyer-ingestion slice after PRs 1-4.
IN PROGRESS: PR 1 (Foundations) merged as #144, 2026-08-14 (AC-F.1 to AC-F.14 plus the PR-1
half of AC-D.17; backend only, Phase 1 exception per the PR-map note). PR 2 (Editable table +
pills) implemented on `fm/spec-pr2-editable-table`, 2026-08-15: AC-A.1 to AC-A.15 and AC-C.1 to
AC-C.4, Phase 1 then Phase 2, with **AC-A.16 (the Playwright e2e spec) outstanding** - browser
verification moved to `agent-browser` by captain ruling mid-slice and the ruling on committed
`e2e/` specs is pending, so no new Playwright spec was written. PR 3 in flight in a parallel lane. PR 4 IN PROGRESS on
`fm/spec-pr4-extraction-prompt` (2026-08-16), contract below.

Also landed out of band: #150, a merge revision joining the `323`/`356` alembic fork that
PRs #144 and #145 created between them. Not a defect in either; see C8's neighbour note and
`alembic/versions/360_merge_container_status_and_spec.py`.

## Goal

Make the spec table the single source of truth for product specifications, and make a person able
to vouch for it. Editable table, paste-once extraction, pill statuses, and a verification workflow
built for a person going through thousands of codes.

The journeys are in the UAC and they come first. This plan is the design that serves them; per
`PRINCIPLES.md` step 0 a plan opening with a schema is a process violation, so the schema below
appears where it belongs - after the journey it exists to support.

## Milestone boundary

Milestone 2 is the supplier portal: a supplier-facing surface, request-scoped tokens, staged
submissions and a second verification identity. **Its UAC and plan are authored separately**
(suggested slug `supplier-spec-portal`). This milestone builds none of it, but carries all eight
seams (M2-S1 to M2-S8 in the UAC) as requirements, because each is cheap now and expensive to
retrofit. The two milestones share exactly one artifact: the verification model, designed once
here and party-scoped from its first migration.

---

## How this plan was produced

The design authority is the `spec-verification-design` report (642 lines) and the
`product-spec-editable` scout investigation (578 lines) beneath it. Neither could reach a database
and neither re-verified every code claim.

Before writing, four read-only DB measurements were taken (the ones the design flagged as
blocking), and four sub-plan investigations were run against real code, each producing
`file:line`-anchored findings. That is the `/wayfinder`-equivalent charting step `PRINCIPLES.md`
requires for module-sized work.

**Process note, stated rather than hidden:** `PRINCIPLES.md` names `/wayfinder`, `/grill-me`,
`/grill-with-docs`, `/to-spec` and `/to-tickets` as pipeline steps. Only `feature` and
`codex-review` exist as skills in this repo; the rest are named but not installed. The
investigation and slicing were therefore performed directly rather than through those skills, and
the grill step ran without a human in the loop, which is a real gap: a grill is a conversation and
this one was self-adversarial. The captain should treat plan review as the first genuine grill.

---

## The four measurements, and what each one changed

All taken 2026-08-13 against the local `sorento_ai_automation` (a copy of prod). Full numbers are
in the UAC's measured baseline table.

| # | Question the design could not answer | Answer | What it changed |
|---|---|---|---|
| 1 | Do `master_data.spec_registry.*` rows exist? | Yes, all four. Granted to **zero roles**. | Bigger than the design assumed. It is not just the `keys-for-product` read: the whole master spec screen is admin-only by accident today. A grant sweep plus two relaxations now ship in PR 2, and PR 3 inherits the blocker. |
| 2 | Flyer blast radius | 756 flyer rows from one import; **3,353** provenance entries, 1,389 rows, **695 codes** (6.1%) | Sizes the promote migration exactly. Also shows the design's "systematic catalogue-wide re-ranking" framing is overstated - flyer is 3.3% of all provenance entries. |
| 3 | Authored values and copy divergence | **Zero** authored entries; **zero** diverging copies | Removes work. The scout's feared convergence migration has nothing to converge; the fan-out is purely forward-looking and **no reconciliation backfill is written**. |
| 4 | `product_suppliers` reality | Default setting NULL; a "DEFAULT" supplier holds 11,412 links, 0 primary; 47.5% of codes have only that link; 11,392 product rows have no link at all | Milestone 2 sizing, recorded for its UAC. The last figure is load-bearing: supplier resolution must go through `product_code`, never `product_id`. |

**All four were taken.** Nothing in this plan is estimated where it could have been measured.

---

## Corrections to the design

The design is followed except where the code says otherwise. Each correction below was verified
against a `file:line` anchor, and each is a case where building the design as written would have
produced something slow, wrong, or dead on arrival.

### C1 - `keys-for-product` returns the numerator, not the denominator (load-bearing, hits PR 2 and PR 3)

The design uses `GET /spec-registry/keys-for-product` as the source of "keys applicable to this
product's class", for both PR 2's add-spec picker (described as "nearly free") and PR 3's coverage
denominator. The endpoint builds its response from `spec.values` - the keys the product **already
holds**. It is the numerator. It is also one query per code and sits behind a permission granted
to nobody.

The scout's supporting citation is dead too: `applies_to_classes` "was never seeded, never read by
anything, and never held a value in any row". Applicability is `applies_when` alone, evaluated by
derivation's `_apply_scope`, where an absent gate value never excludes a key.

**Correction:** a new `applicable_keys_for_code` service, mirroring `_apply_scope`, owned by PR 2
and reused by PR 3. Computed server-side, because milestone 2's pre-seeding calls the same logic
and a second copy of the gate rules on the frontend would drift the first time someone edits
`applies_when`.

### C2 - the permission hole is wider than flagged, and the fix is relaxation plus a scoped sweep

Measured: all four `spec_registry` slugs exist with zero grants; `products.view` has 10 roles,
`.edit` has 9. The precedent for the fix is already in the same file 300 lines above the offending
route: `GET /spec-registry` runs on `master_data.products.view` with the reasoning written into a
comment.

**Correction:** relax the two product-scoped registry reads to `products.view`, **and** sweep
`spec_registry.{view,edit,add}` from the corresponding `products.*` holders. The sweep **excludes
`integration_*` roles** - `integration_n8n`, `integration_sorento_mcp` and
`integration_foundryx_esb` are API-key principals, and letting the n8n parser mint vocabulary keys
inverts the one-source-of-truth guarantee this whole milestone exists to establish. `.delete`
stays ungranted.

### C3 - seeding the boost row without changing the boost branch is a demotion (load-bearing, PR 1 owes PR 4)

`product_spec_search.py` hardcodes `source == "flyer"`. The captain settled `human_source_boost` at
1.5 so the flyer migration is ranking-neutral - but the policy row alone changes nothing. Ship the
row without a source-keyed lookup and PR 4's promote migration becomes a straight 1.5x to 1.0x
demotion for 695 codes, and PR 4 gets blamed for a PR 1 omission.

**Correction:** PR 1 ships the source-keyed branch, and PR 4 verifies it is present before running
the promote migration rather than assuming it. `flyer_source_boost` stays a separate knob so the
two can be retuned apart.

### C4 - an exception is answered by fixing the value, not by a resolve workflow (settled by the captain, 2026-08-14)

The captain settled that a product with open exceptions cannot be verified. That rule stands. The
question was what "resolving" one means, and the answer changed after the 258 blocked codes were
actually inspected rather than counted.

**What they are.** All 258 were pulled and read:

| Reason | Codes | What it really is |
|---|---|---|
| `shape_mismatch` | 237 | **Not a defect.** 212 come from the `length == width` rule (`product_spec_derivation.py:1043-1050`): "the fingerprint of a round or square product forced into rectangular columns". A 1500x1500 tray gets flagged, correctly, and it is *permanently* true. Clustered: 27 codes at 1500x1500, 21 at 415x415, 19 at 460x460. The other 25 are the sibling case where the description says round, so the stored L/W/H are mis-keyed. |
| `column_conflict` | 13 | Description reads `13X8X12`, columns hold 130/80/120 - centimetres against millimetres. The engine already resolves it correctly ("curated data outranks parsed text"); the flag just records that the description disagreed. |
| `company_copies_disagree` | 5 | `brand` differs across the two company copies: `"SORENTO"` vs `"SORENTO, TP ENTERPRISE"`. |
| `implausible_dimension` | 3 | Real description typos: `1300750X620MM` is a missing separator, `1800X1200X7400MM` claims a 7.4-metre height. |

**An intermediate proposal was considered and rejected by the captain:** making the block
reason-specific, so only "genuine" reasons block. Rejected as an unnecessary taxonomy. The people
doing this work are the authority on the catalogue, and the simpler answer is that they correct
the value and the system accepts it.

**The correction, therefore, is the opposite of what this plan first said.** There is **no resolve
action, no dismissal, no reason field and no `resolved_at` carry-forward.** Setting the right
value *is* the resolution, and no justification is asked for.

Two consequences, both of which make this slice smaller:

1. **The existing delete-and-reinsert rebuild is correct and stays.** This plan previously called
   it a defect to fix. It is the mechanism: correct the underlying fact and the flag simply is not
   re-raised, with nothing to carry forward and no second source of truth about what is resolved.
2. **One small code change is required**, without which the model does not actually work:
   `flag()` appends unconditionally (`product_spec_derivation.py:646-649`) and never checks
   whether a human already answered that key, so setting `shape` to square would see
   `round_or_square` return on the very next run. Fix at the rebuild in `derive_for_code`, where
   `spec.provenance` is already in hand: **drop any flag whose `spec_key` carries a value from
   `AUTHORED_SOURCES`**. PR 1 is already restructuring that exact loop, so it lands with work
   that is happening anyway.

**This covers all 258**, because every flagged key is a spec key the editable table can set:
`shape` (212), `diameter` (25), `dim_*` (16), `brand` (5). Nothing is left permanently stuck.

**One limitation to state rather than discover.** Authoring `dim_length` or `brand` as a *spec*
value does not rewrite the `products` column of the same name, so other consumers reading that
column still see the old number. That is consistent with the premise of this milestone - the spec
table is the source of truth for specs - but it means these exceptions are answered rather than
their root cause repaired. Fixing the master column is a separate edit on the product, and for
the 3 typo'd descriptions it is the better fix.

### C5 - the verification screen is a standard list, not a split-pane workbench (settled by the captain)

**Superseded by the captain at plan review, and this replaces the design's section D presentation
entirely.** The design proposed a split-pane workbench and flagged it as a deliberate deviation
needing sign-off. The answer is no: it is a **list of products**, using the shared `DataGrid`
exactly as the user list does, because the objective is **to see many products at once and review
many at once, including bulk actions**.

What this changes:

- **The screen** is a standard server-paginated `DataGrid` list with search, filters, per-row
  checkboxes and the **standard select-all at the top left**, matching every other listing.
- **Bulk verify** is now a requirement, not a prohibition. The design argued against it ("a
  verification nobody looked at is what this feature exists to prevent"); that argument was
  aimed at blind whole-catalogue stamping, and it does not apply to ticking rows you are looking
  at in a grid. It survives only as the narrow guard below.
- **Clicking a product opens the existing product detail page's Specifications tab.** There is
  **no new detail route at all**. That tab is already where the editable table (PR 2), the
  exceptions and the diff live, and `products/[id]` already carries prev/next via
  `ProductNavigation.tsx` feeding `RecordNavigation` in IDs mode. So reviewing one-by-one comes
  for free and is the repo's mandated pattern.
- **The split pane, the prefetch orchestration, the `j`/`k`/`v`/`n` keyboard map and the
  cross-page cursor traversal are all dropped.** Efficiency is served by bulk action plus the
  existing prev/next, which is a smaller build than the workbench and needs no sign-off.
- **The deviation and its outstanding sign-off are moot.** This is now the standard pattern, so
  `PRINCIPLES.md`'s detail-page + `RecordNavigation` mandate is satisfied rather than deviated
  from.

Two things carried forward unchanged: the list is server-paginated (the repo has no
virtualization library and never loads thousands of rows client-side), and **the model, the
schema and every endpoint are untouched by this swap** - which is exactly the property AC-D.16
was written to guarantee, now collected.

**The one guard, measured rather than argued.** The shared select-all is **page-scoped**
(`table.toggleAllPageRowsSelected`, `components/ui/data-grid-select-column.tsx:29-31`). A
cross-page "select all N matching" exists in the shared toolbar but is an explicit per-listing
opt-in (`selectAllMatching`, `data-grid-list-toolbar.tsx:300-307`). Plan: wire the standard
select-all and **do not** opt into `selectAllMatching`, so a bulk stamp can only ever cover rows
that were on screen. "Just like currently" already means page-scoped, so this needs no argument -
but enabling whole-filter selection later is a deliberate decision, not a default.

**Bulk must not become a laxer path.** The bulk endpoint applies the *same* guards as the single
verify - same-transaction hash compare, exceptions still block - and returns **per-code
outcomes** rather than all-or-nothing, so a batch reports "42 verified, 3 skipped, exceptions
open" instead of failing whole or, worse, stamping what the single button would have refused.

**Verify and Unverify are row buttons, not only bulk actions** (captain, 2026-08-14). Each row
carries its own action in an actions column, so a product can be confirmed or withdrawn without
opening it or ticking a box; the button follows the row's state. The row action and the bulk
action call the same endpoints, so a per-row Verify is a bulk of one and there is no second code
path to keep honest. Consequence for the contract: **the worklist response must carry each row's
current `values_hash`**, so a row-level Verify can echo back the hash it was rendered against and
the same-transaction guard applies identically from the list.

### C11 - verification must be manually reversible (captain, 2026-08-14)

Neither the design nor the first draft of this plan let a person withdraw a verification. The only
way out of `verified` was for the system to invalidate it because values moved. That is a gap: a
stamp applied by mistake, or to the wrong product, was permanent until someone edited a value to
force an invalidation.

**Unverify** is now a first-class action, on the row, in bulk, and on the product page.

Two design points it forces, neither of them cosmetic:

1. **A manual withdrawal lands on `unverified`, not `needs_reverify`.** Those states mean
   different things: needs-re-verify says "values moved under a stamp, here is the diff to
   re-check", and a withdrawal has no diff. Rendering it as needs-re-verify with an empty diff
   would misrepresent it and would put the code in the ten-second-recheck queue it does not belong
   in. So the state derivation gains one branch: latest row invalidated with
   `reason='manual_unverify'` reads **unverified**. Unverifying a code that is *already*
   needs-re-verify overwrites that row's reason and clears its diff, which is the deliberate way
   to dismiss a pending re-check.
2. **The table needs `invalidated_by_user_id` / `invalidated_by_name`.** Until now every
   invalidation was automatic, so there was no actor to record and the schema had nowhere to put
   one. A manual withdrawal has an actor, and an append-only ledger that records who vouched for a
   product but not who took it back is only half an audit trail. Both nullable; null means the
   system did it.

The original `verified_by` / `verified_at` stay on the row untouched, so the history answers both
questions. Unverify has no exception gate and no hash compare - you are removing a claim, not
making one - and it is idempotent: unverifying something with no verification history is a no-op
returning current state, not an error. It targets one `party`, so an internal withdrawal cannot
disturb milestone 2's supplier stamp.

### C6 - "worst coverage first" is nearly degenerate

Measured spec-key count per code: median 4, max 14, against a denominator of 45-52. Every product
sits between 0% and 27% coverage, so "worst coverage first" collapses to ascending key count and
sends the reviewer to the emptiest, slowest products first, exactly where throughput matters most.

**Correction:** default order is needs-re-verify first, then unverified **grouped by class then
code** - batching one class at a time is what makes each review fast, because the reviewer holds
one mental model of what a Water Closet should carry. Coverage stays a displayed column and an
explicit sort. This is a query param, so the captain can overrule it without a schema change.

### C7 - the coverage query is not the risk it looked like

Flagged going in as the single biggest unpriced risk. Measured with `EXPLAIN ANALYZE`: **113 ms
with coverage vs 120 ms without**, and 101 ms company-scoped with discontinued excluded. The
registry is 52 rows with 7 gated; coverage is 52 rows hashed once and probed 7 times per row.

**Correction:** compute it inline in SQL. No materialized column, no precomputed table, no refresh
hook. Add materialization only if measured p95 exceeds 400 ms after the joins land - a measured
threshold, not a speculative optimisation. Worth recording that the risk was real in the design's
version: `keys-for-product` per code would have been 8,812 round trips returning the wrong number.

### C8 - the flyer retirement order is wrong in two places

- **Findability breaks at step 2, not step 4.** Its selector filters on `source='flyer'`, which
  the promote migration empties. The panel would keep rendering and quietly report a weaker test
  under the same numbers, which is worse than it being gone. Retire it in the same deploy as the
  migration.
- **Steps 2 and 3 must ship in the same deploy.** The gap is one-directional data loss: step 3
  before step 2 means the next `derive_for_code` on an affected code - fired by the change
  listener on any description edit, not only the nightly job - permanently drops every flyer-only
  value on that code.

### C9 - derivation should not call the choke point; both should call one shared writer

The design says all three writers refactor onto `apply_spec_values`. But the choke point itself
calls `derive_for_code` (so a conflict surfaces in the same click), and derivation is a whole-row
rebuild while the authored write is a per-key patch. Inverting that produces a mutual call or a
mode flag.

**Correction:** both call one `write_spec_row()` and share one `merge_authored_over()`. This
preserves the design's actual intent - one place owns the merge rule, one place decides
invalidation - and makes the hard-fail review rule mechanically greppable rather than a judgement
call: **a write to `spec.values` / `spec.provenance` / `spec.rendered_text` outside
`app/services/product_spec_write.py` is auto-reject.** Verified: exactly three such sites exist
today, so the rule is enforceable from day one.

### C10 - smaller corrections, recorded so they are not rediscovered at implementation

- **A tombstoned key is never conflict-flagged.** Derivation re-derives it every run, so flagging
  it would park a permanent unresolvable row in a table whose contract forbids routine successes.
- **`SpecWorkbench` is already taken** by the master screen's tab shell. The new screen is
  `SpecVerificationWorkbench`.
- **`PillList` already exists** meaning a row of *vocabulary-value* pills, unrelated to section
  C's *status* pills. Do not conflate them.
- **Exclude discontinued codes by default:** 11,415 to **8,812**, a 24% cut and the largest
  workload reduction available for one line of SQL.
- **Stamp `verified_by_name`.** A no-FK `text` user id cannot be joined for a display name, and
  the repo forbids UUIDs in the UI.
- **Extraction applies as one batch call**, not N per-key writes - N would produce N fan-outs, N
  rendered-text rebuilds and N verification diffs for one user action.
- **The spec table renders even when empty.** Today the block is hidden entirely when a product
  has no specs, which is a live breach of the never-hide-a-section mandate that this slice fixes.
- **The prompt dry-run button** will produce a misleading result for `spec_extractor`, which is
  not an assistant node. Hide it for non-assistant keys.
- **`status='authored'`, not `approved`.** `approved` is documented but has never been written,
  and it reads as a verification claim - which is per code, not per row.

### Where the design is over-stated rather than wrong

The design calls the flyer-to-authored move a "systematic re-ranking" of the catalogue. Measured,
it touches 3.3% of provenance entries across 6.1% of codes. Not catalogue-wide. It is still worth
mitigating, because the affected entries concentrate in the two most discriminating keys (`finish`
990, `material` 864) and those 695 codes would move down on exactly the queries they used to win.
The mitigation costs one migration and one branch, so the over-description costs nothing - but it
did make an unmeasured number sound like the biggest thing in the slice. The biggest thing in that
slice is actually the ordering constraint in C8.

---

## PR sequence

Vertical slices with blocking edges, per `/to-tickets` shape. Each PR's issue body links this plan
and the UAC; the files stay the contract and an issue that contradicts the UAC loses.

| PR | Contents | Depends on | Design est. | **Re-estimate** |
|---|---|---|---|---|
| 1 | Foundations: `product_spec_write` with `write_spec_row` + `merge_authored_over`, canonical hash, tombstone + merge change, fan-out, `human_override_conflict`, `AUTHORED_SOURCES`, `status` fix, `human_source_boost` row **and the source-keyed boost branch**, listener backstop | boost decision (settled) | 3-5 d | **5-7 d** |
| 2 | Editable table (A) + pills (C) + inline add-value + add-key picker + `applicable_keys_for_code` + permission relaxation and grant sweep | PR 1 | 5-8 d | **10-14 d** |
| 3 | Verification model + **standard list with per-row and bulk Verify/Unverify** (D) | PR 1; PR 2 for the tab's editable table | 8-12 d | **9-13 d** |
| 4 | Prompt box + extraction proposals (B), batch apply, then promote migration + retirements + full re-derive | PR 1 (incl. the boost branch) | 6-10 d | **9-12 d** |
| | **Milestone 1 total** | | **22-35 d** | **33-46 d** |

### On the estimate difference - reported, not hidden

My total is **33-46 engineer-days against the design's 22-35**: roughly **+11 days**, or
+38% at the midpoint. That is not a rounding error and it is not padding. Every PR came in above
the design's number, and each one for the same reason: the design priced the diff, not the slice.

(The original figure was 35-49. Two captain decisions took it down. The standard list rather than
the split-pane workbench took **2 days off PR 3** - no split pane, no prefetch orchestration, no
keyboard map, no cross-page cursor traversal, and the one-by-one review reuses the product detail
page rather than a new route - with row actions, bulk verify and unverify adding back about
1.5 days. Dropping the resolve workflow in favour of "fix the value" (C4) took off another
**1.5 days**, leaving a few hours for the authored-key flag filter.)

The gap is almost entirely **unpriced items**, not resizing:

- **PR 1 (+2):** restructuring `derive_for_code`'s loop against a 720-line pinning test file;
  building the **first ever** route tests for `product_specifications.py` (it has zero pytest
  coverage today); the `derived_hash` invalidation and immediate re-derive the design never
  mentions; the RQ worker not registering the spec listeners, which would leave the new backstop
  blind on that path.
- **PR 2 (+5-6):** the `keys-for-product` correction (C1) turning a "nearly free" picker into a
  backend service with tests; the permission work being a migration rather than a line change
  (C2); the Specifications tab being a rewrite onto react-query rather than an edit, since it
  calls services directly from `useState` today; the tombstone rendering contract; a shared
  `SearchableSelect` change with cross-product blast radius; inline editing inside `DataGrid`
  cells (D10, roughly a day over the CSS-grid shape it replaces); and the server-side value
  near-duplicate guard (D11, +0.5).
- **PR 3 (+1-2):** hash canonicalisation against 18,403 numeric and 408 array values, each of
  which would otherwise produce phantom invalidations that look like a broken feature; the bulk
  verify and unverify endpoints with per-code outcome reporting rather than all-or-nothing;
  stamping `verified_by_name` and `invalidated_by_name`; and the `spec_registry` grant hole it
  inherits from PR 2. The exception dead end the design left open costs almost nothing to close
  under C4 - a flag filter, not a workflow.
- **PR 4 (+2):** the full-catalogue re-derive (removing the flyer from the input fingerprint
  invalidates all 11,415 codes and rewrites all 22,805 rows - an ops task with verification, not a
  side effect to discover when the nightly job runs long); the findability timing correction
  moving frontend work into the migration deploy; deleting six-plus derivation tests and a whole
  test file, which is slower than writing tests because each deletion must be justified in review;
  and a shipped FE type change the design's retirement list omits.

Some things came in **cheaper** and are netted into the numbers above: no reconciliation backfill
(measurement 3), no virtualization dependency (C5), no coverage materialization (C7), no
`DISTINCT ON` in the worklist, and a 24% smaller worklist from excluding discontinued codes.

**Recommendation:** plan against 35-49 days. If the captain needs a smaller first commitment, PR 1
and PR 2 (14-20 days) deliver the editable table, which is the requirement with the most immediate
daily value, and PR 3 can follow without rework because the model is designed here.

---

## Phase structure per PR

Every PR runs `PRINCIPLES.md`'s three-phase loop. Two are backend-first exceptions to
Phase-1-mock-first, and per the rule that is **stated in the PR description, not silently
skipped**.

### PR 1 - Foundations (backend only; Phase 1 does not apply)

No UI, so there is no UX to settle against a mock. Phase 2 only, test-first.

- **Models/services:** `app/services/product_spec_write.py` with `AUTHORED_SOURCES`,
  `canonical_values_hash`, `write_spec_row`, `merge_authored_over`, `apply_spec_values`.
- **Migration:** exactly one, the idempotent policy seed. **No DDL.** Say so explicitly in the PR
  description, because "a merge-semantics change with no migration" reads as an omission until
  you say why.
- **Routes:** the existing hand-set and clear routes reduced to validation plus a service call;
  the tombstone reachable so it is end-to-end testable. Contracts unchanged, so the shipped FE
  keeps working.
- **Tests (red first):** the resurrection pin; hash canonicality including the numeric, array,
  unit and provenance-exclusion cases; fan-out across copies; conflict once per code and never for
  a tombstone; status precedence; both boost cases; the listener backstop; and the first route
  tests this module has ever had.
- **DoD note for the reviewer:** gate 2 (backfill) binds on exactly one artifact here, the policy
  row, satisfied by the idempotent seed. No column is added to `product_specifications`. Gate 3
  (permissions) does not bind - no new slug.

### PR 2 - Editable table + pills (Phase 1 first)

- **Phase 1 (mock, no backend, no tests):** the `spec-table/` component trio built props-driven
  against fixtures covering every state - derived, flyer, category and authored values, a
  tombstoned key (which per AC-A.5 as amended renders **no row**, so the fixture pins the absence),
  an open conflict, an enum key, a numeric key with a unit, a boolean, a free-text
  key, and a stored key the registry no longer defines. Verify in a real browser by **sidebar
  clicks from `/`**, never a deep link, at 375px and 1280px. Document the contract at the top of
  the service file.
- **Phase 2 (test-first):** `applicable_keys_for_code`, the `similar` endpoint and its server-side
  guard, the split-by-field `PATCH` permission and the appending `POST .../values` route that
  add-a-value ended up on (D18), the two relaxations and the grant
  migration; then the frontend off mocks onto react-query hooks. Delete `AddSpecByHand.tsx` rather
  than leaving it beside the new component.
- **The spec table is the shared `DataGrid`** (D10, captain-settled, overruling this plan's
  earlier CSS-grid proposal): one table component across the system is a design principle, and a
  parallel implementation is exactly the drift the component-library rule exists to prevent. The
  editing concern is solved inside the component, not around it: an edit affordance on the row
  (click the value, or the row's edit icon) swaps the value cell to the shared `SpecValueCell`
  input in place. Columns get explicit `size`; at phone width the grid scrolls horizontally
  inside its own container per the repo's responsive standard. The lifted `AddSpecByHand`
  renderer becomes the cell editor either way, so nothing else in the slice changes.
- **Carry `FlyerCard` across unchanged.** It is the single easiest thing to tidy up by accident,
  and doing so would drag PR 4's decisions into this PR.

### PR 3 - Verification model + list with bulk verify (Phase 1 first)

- **Phase 1:** the list against fixtures - all three states, a code with open exceptions, a code
  with 0 specs and one with 14, a needs-re-verify with a 3-key diff, an empty result, plus the
  **selection and bulk strip**: nothing selected, a partial page selected, a whole page selected,
  and a mixed bulk outcome ("42 verified, 3 skipped"). Two fixtures deserve the captain's
  attention at prototype review: the progress line reads **"0 of 8,812"** on day one, and the
  needs-re-verify state is unreachable with real data until someone makes the first edit.
- **Phase 2 (test-first):** the migration and model; the worklist with inline coverage, ordering,
  filters, summary, pagination and each row's `values_hash`; the single verify endpoint with row
  locking, same-transaction hash compare and a distinguishable 409 taxonomy; the **bulk verify
  endpoint applying the same guards per code and returning per-code outcomes**; the **unverify
  endpoint** (single and bulk) stamping `manual_unverify` plus the actor, idempotent on a code
  with no history; the authored-key flag filter at the exception rebuild (C4); the verification
  block, row actions and single-product Verify/Unverify folded into the existing
  `by-product/{id}` response and the Specifications tab.
- **No new detail route.** Row click goes to `products/{id}` on the Specifications tab, which
  already carries prev/next through `ProductNavigation.tsx`. The worklist is keyed on
  `product_code` and the page is keyed on `product_id`, so the row resolves to the copy in the
  caller's company scope - worth an explicit test, since a code can have two copies.
- **Nav:** a new Master Data leaf. The group already carries the right module key and the backend
  router is already module-guarded, so **no module-guard change is needed**.
- **Permissions:** reuse `products.view` / `.edit`. Minting `master_data.spec_verification.*`
  would ship the feature 403'd to everyone - exactly what happened to the spec registry.

### PR 4 - Prompt box, extraction, flyer discard (Phase 1 first, then a staged migration)

- **Phase 1:** the prompt box and the shared review component against fixtures - a three-kind
  result, a zero-proposal result, a degraded no-model result, and the error and applying states.
- **Phase 2 (test-first):** the extract endpoint returning proposals only; the sibling extractor
  sharing the registry validation helpers plus the scope gate; the `spec_extractor` prompt key
  with zero declared variables and a hardcoded fallback; the batch apply route; then the staged
  migration.
- **Migration runbook** (this is the risky part, and it is a runbook, not a step):
  1. Verify PR 1's source-keyed boost branch is present. Do not proceed without it.
  2. `pg_dump --data-only -t product_specifications` as a pre-flight.
  3. Run the promote migration. Verify the stated before/after counts, and confirm a checksum over
     `values` is **identical** - that is what proves it moved provenance and nothing else.
  4. Same deploy: derivation stops reading the flyer, and findability retires.
  5. Schedule and verify the full-catalogue re-derive.
  6. A later deploy: drop `ProductFlyerText`, after its own `pg_dump`.
  Steps 1-4 are revertible. Step 6 is not.

**Binding amendment (captain, 2026-08-14): the flyer text pass is lifted, not deleted.** Flyer
ingestion becomes a **bulk proposals-review-accept feature**, its own slice after PRs 1-4 (own
UAC and plan; evidence and reasoning: `flyer-spec-ingestion/report.md` sections 5.2-5.3). This
changes PR 4's retirement list in exactly one way, and it is binding on whoever implements it:

- When derivation stops **reading** the flyer, do **NOT** delete the source-major flyer pass, the
  `source: 'flyer'` rule scope, or `_DESCRIPTION_FIRST_KEYS`. **Lift them into a pure
  `propose_from_text(text, code)`** that returns candidate key-values with evidence and writes
  nothing. The seam already exists: `derive_for_code` takes `flyer_text` as a parameter. Deleting
  the pass outright would destroy the extraction knowledge tuned to the real flyer document, and
  the follow-up slice would have to rebuild it from scratch.
- Consequently the "Flyer only" rule-editor scope **stays** (rules scoped to flyer text feed the
  proposal path), and the earlier instruction to strip it is withdrawn. `AC-B.18` is the
  contract.
- **Accepted proposals in that future slice carry a distinct `AUTHORED_SOURCES` member
  (`source='flyer'`), never `source='human'`** - a machine read must not be badged as a person's
  typing. Same conflict-winning, re-derivation-surviving, verification-resetting mechanics as
  `human`; different badge, and `flyer_source_boost` stays an independently tunable knob (C3).
  The membership flip lands in that slice, sequenced **after** the promote migration, never in
  PR 1.
- Everything else in this PR stands unchanged: promote-then-discard (D2), the migration runbook
  above, the paste-once prompt box, and the `ProductFlyerText` drop.

#### PR 4 implementation contract (main session, 2026-08-16; charted against main at `eb2cf0ce`)

Verified before this was written: PR 1's source-keyed boost branch is present
(`product_spec_search.py:822-824`, `source_boosts` keyed by source with `flyer` on its own knob),
so runbook step 1 passes and the promote migration may ship. Main carries TWO alembic heads
(`363_merge_flyer_promo_um`, `365_merge_scm_plan_feedback`) and
`tests/test_alembic_revision_ids.py::test_migration_graph_has_a_single_head` is red on main; this
PR joins them with an empty merge revision before the promote revision.

**Document input (captain's intent, judged here).** The dealer-kit flyer read (PR #184) is a
whole-A3-flyer card extractor (background job, R2 attachment, card geometry, per-code report). It
is not a generic document-to-text path for one product's supplier PDF or photo, and
`AIExtractService` renders PDFs to images for a vision model against a registered form schema,
not the spec registry. Neither reuse is straightforward, so **this PR ships paste-text only** and
reports the document input as a follow-up finding. No new extraction subsystem is built.

**Two engines, one endpoint.** Proposals come from (1) the lifted rule pass
`propose_from_text(text, code)` - deterministic, always run, the flyer-tuned knowledge - and (2)
the LLM sibling `extract_specs_from_text` in `product_spec_understanding`, run when a model is
reachable, adding keys the rule pass did not fire. When no model is reachable the response is
`engine: "deterministic"` (AC-B.5), otherwise `engine: "semantic"` with `model` named. Both go
through the same validation (`_vocabulary` / `_coerce` / `_validated_pairs`) and the same
`_apply_scope` gate as derivation, so neither can propose invented vocabulary or an out-of-class
key (AC-B.4). `understand_phrase` is not touched.

**Backend routes** (in `app/api/v1/master_data/product_specifications.py`, style of the file:
inline permission `Depends(require_permission_with_api_key(...))`, hand-built dict responses):

- `POST /product-specifications/by-product/{product_id}/extract` - `master_data.products.edit`.
  Body `{"text": str}`. 422 with a readable message when blank or over 8,000 characters (no
  truncation). Writes nothing to `product_specifications` or `product_flyer_text` (AC-B.1/B.2; the
  usage log row `understand_phrase` already writes for `spec_search` is acceptable and is not a
  spec write). Response:
  ```json
  {"product_code": "SRT...", "engine": "semantic" | "deterministic", "model": "gpt-4o" | null,
   "proposals": [{"spec_key": "finish", "label": "Finish", "data_type": "enum",
                  "value": "matt black", "unit": null, "evidence": "Matt Black finish",
                  "kind": "new" | "change" | "conflict",
                  "stored_value": "chrome" | null, "stored_unit": null,
                  "stored_source": "derived" | "human" | ... | null}],
   "unchanged": 3}
  ```
  `kind` is computed server-side (AC-B.3): stored key absent -> `new`; stored equal after
  coercion (`_canonical_entry`) -> omitted, counted in `unchanged`; stored provenance authored
  (`AUTHORED_SOURCES`) or tombstoned (`absent: true`) -> `conflict`; stored non-authored and
  different -> `change`, EXCEPT a key in `_DESCRIPTION_FIRST_KEYS` whose stored value came from the
  description, which is `conflict` (this is the lifted "the description beats the flyer for
  sizes" rule, expressed as default-unticked rather than silently applied). One proposal per key;
  `finish` (the multi-value key) may propose a joined value exactly as derivation stores it.
- `POST /product-specifications/by-product/{product_id}/values/batch` - `master_data.products.edit`.
  Body `{"entries": [{"spec_key", "value", "unit"?, "evidence"}]}` (1..50 entries; empty is 422).
  ONE `apply_spec_values(db, code, entries, actor=...)` call with `op="set"`,
  `source="human"`, evidence `"read from text: <evidence>"` (AC-B.9); atomic - any bad entry
  fails the whole batch through the choke point's own validation. Response `{product_code,
  rows_written, spec_keys}` as the service returns it. Nothing else new; the FE refetches
  `by-product` afterwards.
- `PUT .../flyer-text` and the four `/findability/*` routes are DELETED; the by-product response
  drops `flyer_text` (AC-B.14). `product_flyer_import.py` (zero callers) and
  `spec_findability.py` are deleted with `tests/test_spec_findability.py`. The findability
  tables and `ProductFlyerText` model stay (runbook step 6 is a later deploy).

**`propose_from_text(text, code, *, rules_by_key=None, scopes_by_key=None) -> list[dict]`** in
`product_spec_derivation.py` (AC-B.18): pure, no session, writes nothing. Runs `apply_rules`
over `{"flyer": text}` plus the code passes, keeps the source-major order and the `source:
"flyer"` rule scope, applies the same value post-processing (units, `_MM_KEYS`, `MULTI_VALUE_KEYS`)
and `_apply_scope`, and returns `[{"spec_key", "value", "unit", "evidence", "origin":
"flyer"|"code", "description_first": bool}]` where `description_first` is membership in
`_DESCRIPTION_FIRST_KEYS`. `derive()` and `derive_for_code()` lose their `flyer_text` parameter,
`derive_all` its preload, and `_input_hash` its `flyer_text` part (so the fingerprint changes and
AC-B.13's full re-derive is real); `DERIVATION_VERSION` bumps. The seven flyer tests in
`tests/test_product_spec_derivation.py` (:861, :881, :951, :967, :994, :1007, :1019) are lifted
onto `propose_from_text` where they test the pass and deleted where they test the flyer beating or
losing to the description inside one derivation (that ordering no longer exists inside
derivation; its survivor is the `description_first` flag). Shipped rules with `"source":
"flyer"` in `product_spec_registry.py` stay - they feed the proposal path - and the rule editor's
"Flyer only" scope stays.

**Prompt key** `spec_extractor` in `PROMPT_KEYS`: `active=True`, `variables=[]`, hardcoded
fallback (the extraction system prompt: read the pasted text onto the given vocabulary, JSON
`{"specs": [{"key","value","evidence"}]}`, never invent keys or values, quote the words). No
seed migration - `spec_understanding` was added the same way and `get_prompt` falls back to the
hardcoded text when no row exists. Dry-run hiding (C10): the assistant dry-run must not run a
non-assistant key through the chat pipeline. Add `dry_runnable: bool` to `PromptKeySpec` (True
only for the assistant-pipeline keys), surface it from `list_keys()`, have `POST .../test`
refuse with 400 when it is False, and have the FE `PromptDetail` pass
`disabled={!meta.active || !meta.dry_runnable}` with the matching reason. `spec_understanding`,
`scm_market_advisory`, `ideate_extractor` and `spec_extractor` are not dry-runnable.

**Migrations** (`alembic/versions/`, ids <= 32 chars, one head after):
1. `366_merge_flyer_promo_scm_heads` - empty merge of `363_merge_flyer_promo_um` +
   `365_merge_scm_plan_feedback` (repo template: `365_merge_scm_plan_feedback.py`).
2. `367_promote_flyer_provenance` - down_revision `366_...`. UPDATE `product_specifications` SET
   `provenance` = the same object with every entry whose `source = 'flyer'` rewritten to
   `{"source": "human", "confidence": <kept>, "evidence": "flyer: " || <original evidence>,
   "migrated_from": "flyer"}` (other entries byte-identical), and `status = 'authored'` where
   `status = 'derived'` and the row now holds an authored entry - WHERE the row holds at least one
   `source = 'flyer'` entry (mismatch-based, so a second run updates 0 rows and a prior partial run
   is completed by the next run). `values`, `rendered_text` and `derived_hash` are NOT touched.
   `downgrade()` is exact: entries with `migrated_from = 'flyer'` go back to
   `{"source": "flyer", "confidence", "evidence": <with the "flyer: " prefix stripped>}` and
   `status` returns to `derived` where `authored` and no other authored entry remains. The
   docstring states the blast radius (3,353 entries, 1,389 rows, 695 codes measured 2026-08-13)
   and both migrations log before/after counts through `logging`. The pytest runs the upgrade
   twice against a seeded blank schema, asserts the second run changes nothing, asserts an
   `md5(values::text)` checksum per row is identical before and after, repairs a hand-made
   half-promoted row, and asserts the downgrade restores the seeded provenance exactly.

**Runbook doc**: `documentation/plans/master-data/RUNBOOK-flyer-promote.md` - the six steps
verbatim from this plan with the exact SQL for the pre-flight count, the checksum, and the
post-run assertions, the `pg_dump` command, and how the full re-derive is started (`Read the
catalogue again` on the master spec screen, which spawns `derive_product_specs`, or the RQ task
directly) with the counts to compare. Steps 1-4 ship in this PR's deploy; step 5 is run after;
step 6 is a later deploy and is NOT executed here.

**Frontend** (Phase 1 against fixtures, then wired):
- `components/spec-proposals/SpecProposalReview.tsx` - the shared review (AC-B.8): props
  `{proposals: SpecProposal[]; selectedKeys: string[]; onSelectionChange(keys: string[]): void;
  disabled?: boolean}`. `SpecProposal` = the response row above; `kind` is data. Renders on the
  shared `DataGrid` (D10) with `buildSelectColumn`, one row per proposal, badge copy exactly
  **New** / **Changes X to Y** / **Conflicts with your value X**, evidence in a truncated cell with
  `title`. Owns no product identity and imports no service. The parent seeds the selection with
  every non-conflict key (AC-B.7). Fixtures in `components/spec-proposals/__mocks__/`.
- `SpecExtractPanel` in `products/[id]/components/` replaces `FlyerCard` at the same position on
  the Specifications tab: a `Textarea` and one button "Read specs from this" (Journey B). States:
  idle, reading (button busy, textarea locked), proposals (review + "Apply N" + "Discard"), zero
  proposals ("Nothing new in this text" with the `unchanged` count), degraded (`engine ===
  'deterministic'` shows one short line that the rules alone read it), error (Alert with the
  extracted message, text kept), applying (busy), applied (toast, panel resets, table refetches).
  Text lives in component state only. Gated on `master_data.products.edit` like the table.
- Service: `extractSpecProposals(productId, text)` and `applySpecProposals(productId, entries)`
  in `productSpecService.ts`, added to the contract banner; `setFlyerText`, `getFlyers`,
  `runFindability`, `getFindabilityRuns`, `getFindabilityRun`, `FindabilityRun`,
  `FindabilityResult`, `flyer_text` on `ProductSpecDetail`, `FindabilityPanel` and the "Flyer
  check" tab in `SpecWorkbench` are deleted. Hooks: `useSpecExtraction(productId, productCode)`
  beside `useProductSpecTable`, invalidating the same two query keys on apply - the second
  argument because the applicable-keys key is keyed on the CODE, so the hook cannot invalidate
  it from the id alone; `useProductSpecTable` now exports both key builders so there is one
  copy of each.
- `StoredSpecProvenance` gains `migrated_from?: string`; `SpecSourceBadge` shows a
  `migrated_from === 'flyer'` value as "Set by hand" with the evidence line already reading
  "flyer: ..." (AC-B.15) - no new pill colour.
- Phase 1 mocks: the two service functions return fixtures keyed on the pasted text
  (`"nothing new"` -> zero proposals, `"no model"` -> deterministic, `"fail"` -> error, anything
  else -> the three-kind result), swapped for real calls at the service boundary in Phase 2.

---

## Reuse (no new one-offs)

`lib/status-pill.ts`, `SearchableSelect`/`SearchableMultiSelect`, `ConfirmDeleteDialog`,
`DataGrid` (verification list AND the spec table, per D10), `extractApiError`, `buildDataGridParams`, the mutation-hook factories,
`RecordNavigation` via the product page's existing `ProductNavigation`, the existing exception card, the
prompt registry, and derivation's own `_apply_scope` gate rather than a second copy of it.

Two components are built once and consumed twice by design: the editable spec table (product tab
and review pane, and milestone 2's portal) and the proposal review (extraction and milestone 2's
supplier acceptance).

---

## Risks

- **The exception dead end (C4)** would have embarrassed us on day one: 258 codes unverifiable
  with no way out. Closed by the authored-key flag filter, so setting the right value answers the
  flag. The residual risk is shipping the filter late: without it, every one of those 258 rows
  shows a Verify button that always fails.
- **The migration ordering window (C8)** is the one that loses data rather than time. Mitigated by
  shipping steps 2 and 3 together and by an exact, written downgrade.
- **The boost branch omission (C3)** is a cross-PR dependency that fails silently and gets blamed
  on the wrong slice. Mitigated by PR 4 verifying it rather than assuming it.
- **Alembic head forking.** The repo has a single head today, but PR #57 (dealer kit) carries ten
  migrations plus a merge revision. Chain onto the committed head and re-check immediately before
  opening each PR; fix a fork with `alembic merge`, never by editing a landed revision.
- **Dealer-kit collision: investigated, low.** PR #57 touches no `product_spec*`, `product_flyer*`
  or findability file, and the bulk flyer importer is **already dead code on main** (zero callers;
  its source table does not exist in main's migrations). One decision to record rather than a code
  conflict, **revised by the captain 2026-08-14**: flyer readings never re-enter derivation as a
  live input - **a flyer reaches specs only as reviewed proposals**, either one card pasted into
  the prompt box (this milestone) or the bulk proposals-review-accept slice that follows PRs 1-4.
  Both paths propose, a person accepts, and the write goes through `apply_spec_values`. The
  second-source-of-truth risk this line originally guarded against stays guarded: the flyer is
  never again something derivation silently reads.
- **Phantom invalidations** if the canonical hash is wrong - 18,403 numeric and 408 array values
  are live traps, and the symptom (everything permanently needs-re-verify) looks like a broken
  feature rather than a hashing bug.
- **A unit change in the registry invalidates every verification carrying that key**,
  catalogue-wide. Arguably correct, definitely rare, and it must be *stated* in the unit editor
  ("this will require re-verifying N codes") rather than discovered.
- **Cross-company visibility of a verification.** 25 codes exist in one company and not the other;
  a stamp from one company's worklist shows on the other's product page. Correct under the code
  grain, and the one place that grain is visible to a user.

---

## Decisions

### Settled by the captain before planning (built on, not reopened)

`human_source_boost` at 1.5; promote-then-discard for flyer values; three-state value-change
invalidation; staged supplier submissions; evidence behind a badge; `spec_registry.add` for key
creation from the product page; an authored value always wins a conflict.

### Settled here, as planner-of-record (all within the design's own "an engineer can settle" list)

- Tombstone stays `absent: true` inside the provenance entry - no migration, and the merge is
  defensive about the general "authored key, no value" shape anyway.
- An authored write forces an immediate re-derive of the code, matching today's delete path, so a
  conflict surfaces in the same click.
- `status='authored'`, not the documented-but-unused `approved`.
- The RQ worker gains the missing spec-listener registration, folded in with a loud PR note: the
  backstop is dishonest without it. It also fixes a pre-existing hole, which is disclosed rather
  than presented as part of the feature.
- Verification grain is `product_code`; ordering groups by class; discontinued excluded by
  default; server pagination over virtualization; coverage computed inline.

### Settled by the captain at plan review (2026-08-14)

- **The verification screen is a standard list, not a split-pane workbench** (C5). Shared
  `DataGrid` used as the user list uses it, multi-select with the standard select-all, bulk
  actions, and row click into the existing product detail page's Specifications tab. This closes
  the one deviation that needed a sign-off, and it closes it by removing the deviation rather than
  approving it.
- **An exception is answered by fixing the value** (C4), with no resolve action, no dismissal and
  no reason field. Derivation stops flagging a key a person has answered.
- **Bulk verify is required, and Verify/Unverify are row buttons.** The design's blanket "no bulk
  verify" is overruled; it only ever had force against blind whole-catalogue stamping, and it
  survives as the two narrow guards in C5 (page-scoped selection, and bulk applying the same
  per-code rules as the single verify).
- **A verification must be manually reversible** (C11). Unverify is a first-class action; it lands
  on `unverified` rather than needs-re-verify, and it adds `invalidated_by_*` to the ledger.
- **The spec table is the shared `DataGrid`** (D10, 2026-08-14). Design principle: one table
  component across the system, no parallel implementations. This overrules the plan's earlier
  CSS-grid proposal; inline editing is solved inside the component via an edit affordance on the
  row.
- **Duplicate-prevention checks are enforced server-side** (D11, 2026-08-14). "We should not
  trust frontend" - the client-side check stays as a latency courtesy, and the server rejects a
  near-duplicate with a 422, mirroring the key-creation guard. *Superseded in part by D17 (the
  acknowledge flag is withdrawn - a near-duplicate is refused outright) and D18 (the add-a-word
  path is `POST /spec-registry/{spec_key}/values`, not the replacing `PATCH`).*
- **Cross-page `selectAllMatching` stays off** (D12, 2026-08-14). Bulk covers rows the user had
  on screen. Enabling it later is a one-prop change plus a confirm stating the full count.

### Settled by the captain at PR 2 hands-on testing (2026-08-15)

All four are deliberate product orders; the UAC's Journey A, AC-A.2 and AC-A.4 are amended to
match. Do not propose reverting them.

- **Create/edit/add-word affordances are permission-gated in the UI** (D13):
  `spec_registry.add` to create a key, `products.edit` for value writes, either edit grant to
  extend vocabulary. The server remains the actual guard; the UI gating only hides what a user
  cannot do.
- **A dropdown-typed key gets the `SearchableSelect` editor even with an empty vocabulary**
  (D14). The free-text fallthrough is removed on purpose; the empty dropdown's only affordance
  is the add-a-word path, so the first word becomes vocabulary and value together.
- **The fixed-list data type is labeled "Dropdown"** (D15) in both create dialogs
  (`AddSpecificationDialog` and the registry page's `AddSpecKey`) - named after the control the
  user will see.
- **The row's tombstone action is plain "Remove"** (D16), behind the standard "Confirm delete"
  dialog, keeping the durable-absence semantics (survives re-derivation); the second action is
  **"Reset"** (back to derived). These replace the earlier sentence-length labels "This product
  does not have this spec" and "Use what the rules read".

### Settled by the captain at PR 2 review (2026-08-16)

- **A near-duplicate is refused outright - there is NO override** (D17). D11's acknowledge flag
  is withdrawn, and the plumbing is deleted rather than left unreachable: no `acknowledge_similar`
  on the create or update payloads, no `acknowledge_field` in the 422 body, which keeps
  `{error, match}`. Two names for one thing leave a registry answering half of every customer
  question each, and a flag nothing sends only made the code disagree with the product.
- **Adding one word APPENDS server-side** (D18). `POST /spec-registry/{spec_key}/values` takes
  `{value}` alone, re-reads the row under `FOR UPDATE` and appends, gated on the same either-grant
  as the vocabulary-only PATCH field. The PATCH keeps its replace semantics for the registry
  editor, which shows and submits the whole list. The product page was rebuilding that list from a
  cached applicable-keys read, so one merchandiser's add deleted a word another had just added,
  silently - and migration 361 widened who can reach that from registry admins to every holder of
  `master_data.products.edit`.
- **A word struck off a specification is not available from the product page** (D19). It is not
  offered in the value dropdown, its alternative spellings are neither matched nor published in
  the shared vocabulary, and adding it back is refused with a message saying it was taken off and
  that an administrator can restore it on the specification's own screen. Restoring stays a
  registry-admin action. Adding must never report success while storing nothing, and must never
  silently reverse the administrator's decision by un-striking the word. Two deeper defects in
  the same area are known, deliberately out of scope for this PR, and tracked as **issue #183**:
  wording left orphaned when an administrator deletes a staff-added value, and a restore
  republishing a word that has since become a value in its own right.

### Outstanding - still the captain's call

None. Every question raised during planning has been answered.

---

## Filed separately

**Issue #139** - the `product_spec` embedding queue has a consumer and no producer;
`enqueue_spec_embedding` has zero callers monorepo-wide, and `product_spec` has zero rows in both
`embedding_queue` and `embedding_documents` while the neighbouring `product` type has 11,401
documents. Semantic spec search has never been fed. **This predates all of this work** and hand
edits will not move it, but it will be blamed on this milestone the first time someone edits a
spec and semantic search does not move. Not fixed here. The cheapest time to fix it is right after
PR 1, when `apply_spec_values` gives it a single correct call site.

## Follow-ups this PR deliberately does not take

- New domain vocabulary (authored value, tombstone, values hash, party, needs-re-verify) has no
  glossary entry; `CONTEXT.md` covers no spec terms at all today. This PR touches only
  `documentation/plans/master-data/`, so the glossary and any ADR are a follow-up.
- Converting the master spec list's hand-rolled table to `DataGrid` - pre-existing debt, wrong
  blast radius for these PRs.
- Dropping the findability tables once their surfaces retire.
