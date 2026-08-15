# UAC - Spec Authoring and Verification (milestone 1)

> Given/When/Then contract for milestone 1 of the product-specification overhaul.
> Governs: `PRINCIPLES.md` + `documentation/reference/ADR-PRODUCT-STANDARDS.md`.
> Plan: `PLAN-spec-authoring-verification.md`. Milestone 2 (the supplier portal) has its own
> UAC and is authored separately - see "Milestone 2 seams" below for what this milestone owes it.

**Slug:** `spec-authoring-verification` · **Domain:** master-data · **Milestone:** 1
**Classification:** CORE, schema `public`, normal FKs (per `PRINCIPLES.md` modular-architecture
rule: products and their specifications are a base-platform capability every install needs).
**Status:** ACCEPTED - captain-reviewed 2026-08-14, the contract for milestone 1. Amended
2026-08-15 per captain decisions at PR 2 hands-on testing (see the plan's Decisions section):
editor and action-label wording in Journey A, AC-A.2 and AC-A.4. Implementation progress is
tracked in the plan's Status line, not here.

## Scope

Make the spec table the single source of truth for product specifications, and make a person
able to vouch for it.

- **A** - the spec table becomes editable: add, edit, remove, with a dropdown for every
  dropdown-typed key (even one whose vocabulary is still empty) and free text otherwise, and a
  real removal (a tombstone) rather than today's "revert to derived".
- **B** - the stored flyer card becomes a paste-once prompt box: extraction proposes, a person
  reviews, accepted rows write as authored values, the pasted text is never stored. Then the
  flyer-derived values are promoted to authored and `ProductFlyerText` is discarded.
- **C** - spec statuses render as pills, matching the existing `lib/status-pill.ts` vocabulary
  the rest of the system already uses.
- **D** - a verification workflow: a **product list** built for reviewing many at once, with
  per-row and bulk Verify/Unverify, a stamp recording who and when, an automatic reset when the
  values change, and a manual withdrawal when a person changes their mind.

**Not in scope:** the supplier portal (milestone 2). Its seams are requirements here (M2-S1 to
M2-S8) but no supplier-facing surface is built in this milestone.

## Sources

This UAC implements a design produced and reviewed before it: the `spec-verification-design`
report (642 lines) and the `product-spec-editable` scout investigation (578 lines) underneath it.
The design is the authority on the shape of the solution. Four sub-plan investigations against
real code and the live database were run while writing this UAC; where they found the design's
factual premises wrong, this UAC follows the code and the PLAN records the correction.

## Locked decisions (captain-settled - do not reopen)

| # | Decision |
|---|---|
| D1 | **`human_source_boost` seeded at 1.5**, matching the existing `flyer_source_boost`, so the flyer migration is ranking-neutral on day one. |
| D2 | **Flyer-derived VALUES are promoted to authored before the flyer text is dropped** - re-stamped `{"source": "human", "evidence": "flyer: <original>", "migrated_from": "flyer"}` - and only then does `ProductFlyerText` go. The values are not allowed to disappear on the next derivation. |
| D3 | **Verification resets on VALUE CHANGE, three states** (unverified / verified / needs-re-verify), keyed on a canonical values hash through a single write choke point, with the before/after diff recorded on invalidation. Not "an edit happened", and not human-edits-only. |
| D4 | **Supplier submissions are staged for review**, never written directly into `product_specifications`. Milestone 2, but the milestone 1 seams must allow it. |
| D5 | **The verification screen is a standard list, not a split-pane workbench.** Settled by the captain at plan review, superseding the design's workbench proposal. It uses the shared `DataGrid` list component exactly as the user list does: multi-select with the standard select-all, filters, search, and **bulk actions**. The objective is to see and review many products at once. Clicking a product goes to **the existing product detail page's Specifications tab** - no new detail route. Since this is the repo's standard pattern, the deviation and its sign-off are moot. |
| D6 | **Provenance evidence is kept**, as a source badge with the evidence behind hover/expand, rather than a permanent column of text. |
| D7 | **Creating a spec key from the product page requires `master_data.spec_registry.add`** - the same grant as the master screen, no new permission. Duplicate prevention is a UX obligation: match against existing keys and synonyms and offer the match before allowing a create. |
| D8 | **An authored value always wins a conflict.** When derivation later disagrees with a hand-set value, the authored value stays in force and the disagreement is raised as `ProductSpecException(reason='human_override_conflict', ...)` on the existing "Needs a human" card until a person resolves it. **A product with open exceptions cannot be verified.** |
| D9 | **An exception is answered by setting the correct value, and nothing else.** No resolve action, no dismissal, no reason field, no justification. The people doing this work are the authority on the catalogue; asking them to explain themselves to the system is bureaucracy, not control. Derivation therefore stops flagging a key once a person has answered it (AC-D.17). |
| D10 | **The spec table uses the shared `DataGrid` component - design principle, no parallel table implementations.** Settled by the captain, overruling the plan's CSS-grid proposal. Inline editing concerns are solved inside the component (edit icon / click swaps the value cell to an input), not by building a different table. |
| D11 | **Never trust the frontend alone - every duplicate-prevention check is enforced server-side.** The client-side check is a latency courtesy; the API is the guard. Applies to key creation (AC-A.10) and value creation (AC-A.11) alike. |
| D12 | **Cross-page select-all stays off.** Bulk actions cover rows the user had on screen. |

## Measured baseline (fresh, 2026-08-13, local DB = a copy of prod)

The design and the scout both flagged four measurements they could not take. All four were taken
before this UAC was written, plus further measurements during sub-plan investigation.

| # | Question | Measured |
|---|---|---|
| M1 | Do `master_data.spec_registry.*` permission rows exist? | **Yes, all four** (`view`/`add`/`edit`/`delete`). They are granted to **ZERO roles**, while `master_data.products.view` is granted to 10 and `.edit` to 9. |
| M2 | Flyer blast radius | **756** `product_flyer_text` rows (756 codes), all from one import. **3,353** provenance entries with `source='flyer'`, across **1,389** spec rows and **695** codes (6.1%). Flyer is 3.3% of all provenance entries. |
| M3 | Authored values and company-copy divergence | **ZERO** `source='human'` entries anywhere. **ZERO** codes whose company copies disagree on `values`. 22,805 spec rows across 11,415 codes. `status`: derived 22,289 / needs_review 516. |
| M4 | `product_suppliers` reality | `default_product_supplier_id` is **NULL**. A supplier named "DEFAULT" holds 11,412 links with **0 primary**. 5,417 codes (47.5%) have only the DEFAULT link. Supplier links exist on only 11,413 of 22,805 product rows, so supplier resolution must go through `product_code`. |
| M5 | Registry size and gating | **52 active** registry keys, only **7** carrying a non-empty `applies_when`. `applies_to_classes` is dead code, never seeded and never read. |
| M6 | Live vs discontinued codes | 11,415 total, **2,727 discontinued, 8,812 live**. |
| M7 | Open exceptions | **258 codes** carry open exceptions: 237 `shape_mismatch`, 13 `column_conflict`, 5 `company_copies_disagree`, 3 `implausible_dimension`. |
| M8 | Stored value shapes | 81,304 string, **18,403 number**, 1,774 boolean, **408 array**. Spec-key count per code: median 4, max 14. |
| M9 | Worklist query cost | Coverage computed inline in SQL measured at **113 ms** vs **120 ms** without it, and **101 ms** company-scoped with discontinued excluded. Coverage is free; no materialization needed. |

Consequences carried into the ACs: M1 makes a grant sweep mandatory in-milestone (AC-A.11). M3
means there is no drift to reconcile, so the fan-out is purely forward-looking (AC-F.4). M5
invalidates the design's coverage source (AC-D.7). M6 cuts the worklist 24% (AC-D.6). M7 means
the exceptions-block-verify rule is a dead end unless a person's correction stops the flag
re-raising (AC-D.17). M8 names the hash canonicalisation traps (AC-F.10).

---

## Journey

Per `PRINCIPLES.md` step 0, the journey comes before any entity, table or endpoint. Every AC
below traces to a step here.

### Journey A - the merchandiser correcting a spec

**Actor:** a merchandiser holding `master_data.products.edit`. **Arrives from:** Master Data ->
Products -> a product -> the Specifications tab, because a spec is wrong or missing.

**What the system already knows:** every current value, which source it came from, the words it
was read from, which keys this product's class can carry, and the vocabulary each key allows.
None of that is asked for.

1. They see the table. Each row shows its value and a **source badge**; the evidence sits behind
   the badge on hover and behind a tap-to-expand strip on touch, not in a column of its own.
2. **Edit** - they click a value. It swaps to an input **in place**: a dropdown when the key's
   data type is dropdown - even while its vocabulary is still empty, where the add-a-word row is
   the only affordance, so the first word becomes vocabulary and value together - Yes/No for a
   boolean, free text otherwise (amended 2026-08-15, captain). The unit is shown as a suffix and
   is never typed. Nothing on the page moves. Save writes it as authored.
3. **The word is not in the list** - before offering to create anything, the system checks what
   they typed against every value and every customer synonym the key already holds, normalised.
   If "Brushed Brass" already exists for "brushed brass" it offers that instead. Only when
   nothing matches does the dropdown's last row read `Add "brushed brass" to Finish`.
4. **Add a spec** - "Add a specification" offers the keys this product's class can carry that it
   does not already hold, everything else one click away. If genuinely nothing matches, a create
   dialog opens, and before it will submit it checks the proposed label against every existing
   key, label and synonym and offers the match instead.
5. **Remove** - the row's menu offers the two intents as **"Remove"** (a tombstone that survives
   re-derivation, behind the standard "Confirm delete" dialog) and **"Reset"** (revert to
   derived, with its own confirmation). Labels amended 2026-08-15 by the captain from the earlier
   sentence-length names; the semantics are unchanged.

**They leave with:** the table showing exactly what they set, badged as theirs, and a promise the
next catalogue run cannot undo it.

### Journey B - the merchandiser holding marketing text

**Actor:** the same merchandiser. **Arrives with:** a flyer card, a leaflet paragraph, or a
supplier PDF blurb - text stating specs the product master never did.

**What the system already knows:** the product, its class, which keys can apply to it, the whole
registry vocabulary and every synonym, and every value currently stored with its source. The only
thing it cannot know is the sentence in the user's hand.

1. Where the flyer card used to be there is one box and one button. They paste and press **"Read
   specs from this"**.
2. The system returns **proposals, not changes**, each already judged against what is stored:
   **New**, **Changes chrome to matt black**, **Conflicts with your value chrome**. Conflicts
   arrive unticked, the rest ticked. Anything the text merely restates is omitted entirely, so
   the list is short enough to actually read.
3. They untick what they do not want and press Apply. Accepted rows land as authored values in
   one batch, each carrying the words it was read from.
4. The pasted text is gone the moment the component unmounts. It was never stored.

**They leave with:** a table that says what the flyer says, with no second source of truth behind
it and no card to keep in sync.

### Journey C - anyone reading a status

**Actor:** any user on any spec surface.

They read state the same way they already read it on Complaints, purchase requests, stock
inquiries and certificates: a soft pastel pill, same shape, same palette, same meaning per
colour. Nothing new to learn. This is a presentation change only.

### Journey D - the person making the catalogue trustworthy

**Actor:** a merchandiser, or the captain. **Arrives from:** the sidebar, Master Data -> Spec
Verification. They have no list to prepare, no export, no spreadsheet.

**What the system already knows:** every spec, its source, what changed since the last verify,
every open exception, and how complete each code's coverage is.

1. **First screen** - a **list of products**, the same shared `DataGrid` the user list uses, and a
   progress line: **"Verified 0 of 8,812 live codes"**. Each row carries the code, class, brand,
   coverage, open-exception count and a verification pill, so **many products are reviewable at a
   glance without opening any of them**. Discontinued products are excluded by default with a
   toggle. The order is the work order: needs-re-verify first (ten-second diffs), then
   never-verified, grouped by class so the reviewer holds one mental model at a time. Filters
   live in the URL so a person can own a slice and resume tomorrow.
2. **Acting on one row, without leaving the list** - every row carries its own **Verify** button.
   A product that reads correctly at a glance is confirmed right there, one click, no navigation.
   A row already verified shows **Unverify** instead.
3. **Acting on many at once** - the standard select-all sits at the top left of the grid exactly
   as it does elsewhere. The user ticks the rows that are right and presses **Verify selected**;
   the confirmation states the count. **Unverify selected** is offered the same way. This is what
   makes 8,812 codes tractable.
4. **Reviewing one properly** - clicking a product opens **the existing product detail page on its
   Specifications tab**, which by then is the editable table from Journey A. Open exceptions and,
   for a needs-re-verify code, a diff of what changed since the last verify, sit alongside it.
   They fix what is wrong and press **Verify** there. The page already carries prev/next record
   navigation, so the next product is one click away without returning to the list.
5. **Changing their mind** - a verification is never a one-way door. **Unverify** withdraws the
   stamp and the code reads plainly **unverified** again, not "needs re-verify", because nothing
   changed and there is no diff to show. The history keeps both facts: who vouched for it, and who
   took it back.
6. **End state** - the code carries "Verified - <name>, <date>" as a pill wherever it appears,
   in the list and on the product page. Any later change to its values flips it to "Needs
   re-verify" with the diff waiting. Work is never silently discarded; it degrades to a visible
   ten-second re-check, or a person withdraws it deliberately.

**Day-one reality, measured:** 0 codes verified and 0 authored values in the entire catalogue.
The screen opens on a 100% machine-derived, 0% verified catalogue, and the needs-re-verify
path cannot occur naturally until someone makes the first edit. Every AC is written for that
starting state and its tests must manufacture the changed case.

---

## Acceptance criteria

Grouped by slice. Tags: `[BE]` backend, `[FE]` frontend, `[E2E]` Playwright, `[T]` test-only,
`[M]` migration.

### F - Foundations (PR 1, backend only, no UI)

- **AC-F.1** `[BE]` GIVEN any caller writing spec values WHEN the write happens THEN
  `spec.values` / `spec.provenance` / `spec.rendered_text` are assigned in exactly one place,
  `app/services/product_spec_write.py`. Both the authored path (`apply_spec_values`) and
  derivation call the shared `write_spec_row()`, and both share one `merge_authored_over()`.
  A write to those columns outside that module is an auto-reject code-review rule.
- **AC-F.2** `[BE]` GIVEN a spec key a user has tombstoned WHEN `derive_for_code` next runs THEN
  the key does **not** reappear in `values`, and its provenance keeps
  `{"source": "human", "absent": true}`.
- **AC-F.3** `[T]` GIVEN the documented resurrection trap - a provenance-only tombstone under
  today's merge - WHEN the pinning pytest runs THEN it fails against the current merge line for
  the right reason (the derived value returns badged as human-set) and passes against the changed
  one.
- **AC-F.4** `[BE]` GIVEN a hand-set value on a code with more than one company copy WHEN the
  write commits THEN **every** row sharing that `product_code` carries the same value, under the
  all-companies scope, in the caller's transaction. GIVEN the measured baseline of zero authored
  entries and zero diverging copies (M3) THEN **no reconciliation backfill is written**, and the
  PR description states that with the measurement rather than assuming it.
- **AC-F.5** `[BE]` GIVEN derivation produces a value for a key an authored value already holds,
  and the two differ after normalisation, WHEN the merge runs THEN the **authored value stays in
  force** and a `ProductSpecException(reason='human_override_conflict', proposed=<derived>,
  stored=<authored>)` is raised once per code, never once per copy (D8).
- **AC-F.6** `[BE]` GIVEN a **tombstoned** key WHEN derivation runs THEN it raises **no**
  conflict. Derivation re-derives that key every run, so flagging it would park a permanent
  unresolvable row in a table whose contract forbids routine successes.
- **AC-F.7** `[BE]` GIVEN the merge, the search boost branch and the FE source labels WHEN they
  test authorship THEN they test membership in an `AUTHORED_SOURCES` constant, never `== 'human'`.
  `'supplier'` is reserved now (M2-S1). A third member is coming: the bulk flyer-ingestion slice
  after PRs 1-4 stamps accepted proposals **`source='flyer'` as a distinct `AUTHORED_SOURCES`
  member, never `source='human'`** - a machine read badged as a person's own work is the
  dishonesty this milestone exists to remove. The membership flip lands **in that slice, after
  the promote migration has run**, never in PR 1 - flipping it earlier would make legacy
  machine-derived flyer entries count as authored in the merge.
- **AC-F.8** `[BE]` GIVEN a spec row that is wholly or partly authored WHEN derivation runs THEN
  `spec.status` becomes `authored`, with precedence `needs_review` > `authored` > `derived`. The
  documented-but-never-written `approved` value is **not** reused; it reads as a verification
  claim, and verification is per code, not per row.
- **AC-F.9** `[BE][M]` GIVEN the search policy table WHEN the seed migration runs THEN a
  `human_source_boost` row exists at **1.5** (D1), seeded idempotently the same way
  `flyer_source_boost` was.
- **AC-F.10** `[BE]` GIVEN the ranker WHEN it applies a source boost THEN it reads a
  **source-keyed lookup**, not a hardcoded `source == "flyer"` branch. Seeding the policy row
  without changing the branch is explicitly insufficient: it would leave the PR 4 promote
  migration as a straight 1.5x to 1.0x demotion for 695 codes. `flyer_source_boost` stays a
  separate knob so the two can be retuned apart.
- **AC-F.11** `[T]` GIVEN two callers producing the same logical value set WHEN each computes the
  canonical values hash THEN the hashes are equal. The hash covers `values` only and **never
  provenance**, so a re-stamped evidence string or a source change cannot un-verify an identical
  set. It normalises the measured traps (M8): `407` and `407.0` hash alike (18,403 numeric
  values), array values are order-insensitive (408 array values), a missing/null/empty unit
  normalises alike, and booleans are tested before ints.
- **AC-F.12** `[BE]` GIVEN an authored write WHEN it commits THEN `derived_hash` is cleared on
  every touched row, so derivation's skip path cannot suppress the conflict computation, and the
  code is re-derived in the same transaction so a conflict surfaces in the same click.
- **AC-F.13** `[BE]` GIVEN anything writing spec values around the service WHEN the mapper-level
  listener fires post-commit THEN it is detected and logged as a bypass. This is a backstop, not
  the primary path, and it registers on the RQ worker as well as the API process.
- **AC-F.14** `[T]` Every new pytest runs on **Postgres only** via `tests/_pg_fixture.py`, seeds
  its own FK chain with a marker prefix, and borrows no existing row (CI's database is empty).

### A - Editable spec table (PR 2)

- **AC-A.1** `[FE]` GIVEN the Specifications tab WHEN the spec table renders THEN it is the
  **shared `DataGrid` component**, the same one every table in the system uses (D10) - with
  `tableLayout: {width:'fixed', columnsResizable:true}`, explicit `size` per column, and
  truncate + title on long text. **No parallel table implementation.**
- **AC-A.1b** `[FE]` GIVEN a row WHEN its edit affordance is used (click the value or the row's
  edit icon) THEN the value cell swaps to an input **in place** - the cells keep their DOM order
  and nothing reflows. On a narrow screen the grid scrolls horizontally inside its own container,
  per the repo's responsive standard; the page never scrolls sideways.
- **AC-A.2** `[FE]` GIVEN a spec key WHEN its editor renders THEN a boolean gets Yes/No, a
  dropdown-typed key or a key with a non-empty merged vocabulary gets a `SearchableSelect` -
  **even when the vocabulary is empty**, in which case the add-a-word row is the only affordance
  and there is no free-text fallthrough (amended 2026-08-15, captain) - and anything else gets a
  typed input. The **unit renders as a suffix and can never be typed**. A stored key the registry
  no longer defines renders read-only rather than crashing.
- **AC-A.3** `[FE]` GIVEN any dropdown in this slice THEN it is
  `SearchableSelect`/`SearchableMultiSelect`; a raw `<select>` or `@/components/ui/select` is an
  auto-reject. Optional selects are `clearable`.
- **AC-A.4** `[FE]` GIVEN the remove control WHEN it is used THEN the two intents are offered as
  **"Remove"** (tombstone, behind the standard "Confirm delete" dialog) and **"Reset"** (revert
  to derived) - labels amended 2026-08-15 by the captain, semantics unchanged - each behind a
  confirmation dialog. `confirm()` is never used.
- **AC-A.5** `[FE]` GIVEN a **tombstoned** key WHEN the table renders THEN it still shows a row.
  The table model is the **union** of the `values` keys and the `absent` provenance entries, since
  a tombstone lives only in `provenance`. The row reads "Not on this product" with a revert
  action.
- **AC-A.6** `[FE]` GIVEN a row WHEN it renders THEN it shows a **source badge** with the evidence
  behind hover **and** a tap-to-expand strip (hover `title` is unreachable at 375px, which is a
  DoD gate). There is **no permanent evidence column** (D6). For an authored row the strip is
  labelled "Set by", not "Read from", because the stored string is an audit stamp.
- **AC-A.7** `[BE]` GIVEN the add-spec picker needs the keys a product **may** carry WHEN it asks
  THEN it calls a new `applicable_keys_for_code` service that mirrors derivation's `_apply_scope`
  gate. `GET /spec-registry/keys-for-product` is **not** the source: it returns the keys the
  product already **holds**, built from `spec.values`, and `applies_to_classes` is dead code
  (M5). Applicability is `applies_when` alone, and absence of a gate value never excludes a key.
- **AC-A.8** `[FE]` GIVEN the picker WHEN it opens THEN keys this product may carry and does not
  hold come first, everything else behind one more click.
- **AC-A.9** `[FE]` GIVEN the picker finds no matching key WHEN the create dialog opens THEN it
  is gated on `master_data.spec_registry.add` (D7); a user without the grant sees the picker
  **without** the create option plus one line saying who to ask.
- **AC-A.10** `[FE][BE]` GIVEN a proposed new key label WHEN the create dialog validates THEN a
  new `GET /spec-registry/similar` runs a normalised match against every existing `spec_key`,
  label **and merged synonym**, and on a hit offers the existing key instead. The guard is also
  enforced server-side on `POST /spec-registry`, so no other client can bypass it.
- **AC-A.11** `[FE][BE]` GIVEN a value dropdown with no match WHEN the create row is used THEN
  the value is added to that key's `user_values` after a normalised near-duplicate check against
  merged values **and** merged synonyms - **enforced on the server** (D11): the `PATCH` route
  rejects a near-duplicate `user_values` addition with a 422 carrying the match, and accepts it
  only with an explicit acknowledge flag, mirroring the key-creation guard in AC-A.10. The FE
  runs the same check client-side first, against data it already holds, so the common case never
  round-trips - but the frontend check is a courtesy, never the guard.
- **AC-A.12** `[FE]` GIVEN the spec table component WHEN it is written THEN it is
  **props-driven** - values, vocabulary and callbacks in, **no `apiFetch`, no service import, no
  react-query inside the cells** - and it lives in a folder milestone 2's `(auth)`-group portal
  can import (M2-S3).
- **AC-A.13** `[BE][M]` GIVEN the measured fact that all four `master_data.spec_registry.*` slugs
  are granted to **zero roles** (M1) WHEN this slice ships THEN both halves land: the two
  product-scoped registry reads are relaxed to `master_data.products.view` (the precedent and its
  written reasoning already exist on `GET /spec-registry`), **and** an idempotent grant migration
  sweeps `spec_registry.{view,edit,add}` from the corresponding `products.*` holders. The sweep
  **excludes `integration_*` roles** - they are n8n / MCP / ESB API-key principals, and granting
  them key creation inverts the registry's one-source-of-truth guarantee. `.delete` stays
  ungranted. `PRINCIPLES.md` DoD gate 3.
- **AC-A.14** `[FE]` GIVEN a product with no specifications WHEN the tab renders THEN the section
  still renders with an explicit empty state and an "Add a specification" CTA. Today the block is
  hidden entirely when empty, which is a live breach of the never-hide-a-section mandate.
- **AC-A.15** `[FE]` GIVEN the flyer card WHEN this slice ships THEN it is carried across
  **unchanged**. It is PR 4's to replace and its migration is gated on decisions this slice does
  not own.
- **AC-A.16** `[E2E]` GIVEN a user WHEN they navigate **by sidebar clicks from `/`** to a
  product's Specifications tab THEN they can edit a value, add a spec, add a value, tombstone a
  spec and revert a spec, each asserting the expected `/api/v1/*` call, with a clean console, at
  **375px and 1280px**.

### C - Pill statuses (PR 2, ships with A)

- **AC-C.1** `[FE]` GIVEN the spec status vocabulary WHEN pills render THEN they use the existing
  `lib/status-pill.ts` (`STATUS_PILL_BASE` + `statusPillClass`), extended with `derived`,
  `needs_review`, `authored`, `findable`, `not_findable`, `verified`, `needs_reverify` and
  `unverified`. All colours already exist in the family, so **zero new palette is invented**.
- **AC-C.2** `[FE]` GIVEN a provenance **source** badge WHEN it renders THEN it maps onto the
  shared vocabulary through a **local code map**, following the established pattern, rather than
  adding one-domain words like `flyer` or `category` to the shared cross-domain vocabulary. An
  authored source takes the affirmative blue the existing `manual` badge uses; machine sources
  take `ai`'s muted grey.
- **AC-C.3** `[FE]` GIVEN this slice WHEN it is reviewed THEN it contains **zero data changes and
  zero new endpoints**. The three verification colour keys are registered here without a call site
  so no later slice invents a second palette for the same states (M2-S7).
- **AC-C.4** `[T]` GIVEN each converted call site WHEN vitest runs THEN the pill class for each
  status key is asserted.

### D - Verification workflow and product list (PR 3)

- **AC-D.1** `[BE][M]` GIVEN the verification model WHEN it is created THEN it is a new
  **append-only, party-scoped** `product_spec_verifications` table keyed on **`product_code`**,
  carrying `party`, `supplier_id`, `verified_by_user_id` (text, no FK, so history survives user
  deletion), `verified_by_name`, `verified_at`, `values_hash`, `invalidated_at`,
  `invalidated_reason`, `invalidated_diff`, and **`invalidated_by_user_id` / `invalidated_by_name`
  (both nullable, null meaning the system did it)**, with a partial unique index on
  `(product_code, party) WHERE invalidated_at IS NULL`. There is **never** a `verified_at` column
  pair on `ProductSpecifications` (M2-S2). The table is deliberately **not** company-scoped,
  matching every other spec table.
- **AC-D.2** `[BE]` GIVEN a code WHEN its state is read THEN it is **derived, never stored**: no
  rows = unverified; an active row = verified; no active row whose latest invalidation reason is
  `manual_unverify` = **unverified**; no active row with any other invalidation = needs re-verify,
  and the diff and the original credit come from the latest invalidated row. A read never re-hashes
  values to decide the pill.
- **AC-D.3** `[BE]` GIVEN a verified code WHEN its effective values change THEN **every** active
  row for that code is invalidated regardless of party, with `invalidated_reason` and a
  before/after `invalidated_diff` (D3, M2-S5), and `invalidated_by_*` left null because no person
  did it. GIVEN derivation's skip path (unchanged derived hash) THEN nothing is invalidated.
- **AC-D.20** `[BE][FE]` GIVEN a verified code WHEN a user chooses **Unverify** THEN the stamp is
  withdrawn and the code reads **unverified**, not needs-re-verify: a withdrawal has no diff, and
  showing a re-verify prompt with an empty diff would misrepresent it. The action stamps
  `invalidated_reason='manual_unverify'`, `invalidated_by_user_id` / `invalidated_by_name` and a
  **optional short reason**, leaves `invalidated_diff` null, and **preserves the original
  `verified_by` / `verified_at` on the row**, so the history still answers "who vouched for this,
  and who took it back".
- **AC-D.21** `[BE]` GIVEN a code that is already **needs-re-verify** WHEN the user unverifies it
  THEN it also becomes unverified: the latest row's invalidation reason is overwritten to
  `manual_unverify` and its diff cleared. This is the deliberate way to dismiss a pending
  re-check ("I am not re-confirming this, treat it as never verified"). GIVEN a code with no
  verification history WHEN unverify is called THEN it is an **idempotent no-op** returning the
  current state, never an error.
- **AC-D.22** `[FE]` GIVEN a row in the product list WHEN it renders THEN it carries its own
  **Verify / Unverify button in an actions column**, so a product can be verified or withdrawn
  **without leaving the list or opening it**. The button follows the row's state: an unverified or
  needs-re-verify row offers **Verify**; a verified row offers **Unverify**. Only the row acted on
  changes; the rest of the grid stays interactive and the list does not re-sort under the user's
  cursor.
- **AC-D.23** `[FE]` GIVEN rows are selected WHEN the bulk strip is active THEN **Verify selected**
  and **Unverify selected** are both offered, under the same page-scoped selection rule, each with
  a confirmation stating the count. The row buttons and the bulk actions call the same endpoints,
  so a per-row Verify is a bulk of one.
- **AC-D.24** `[BE]` GIVEN the worklist response WHEN it is served THEN each row includes its
  current `values_hash`, so a row-level Verify can echo back the hash it was rendered against and
  the same-transaction guard in AC-D.4 applies identically from the list. A row whose values moved
  since the page loaded is refused with `values_changed` and the row refreshes rather than
  silently stamping something the user never saw.
- **AC-D.25** `[FE]` GIVEN a single product's Specifications tab WHEN it is verified THEN an
  Unverify control sits beside the verification pill, behind its own confirmation.
- **AC-D.26** `[BE]` GIVEN unverify WHEN it is gated THEN it uses `master_data.products.edit`, the
  same grant as verify, and **a user may withdraw a stamp that is not their own** - the recorded
  actor is what makes that accountable rather than the permission. GIVEN `party` WHEN unverify
  runs THEN it targets one party only, so milestone 2's supplier stamp is untouched by an internal
  withdrawal.
- **AC-D.4** `[BE]` GIVEN a verify request WHEN it is served THEN the client echoes the hash it
  was shown, the handler locks the code's spec rows and compares in the same transaction, and it
  409s with a distinguishable code when the values moved (`values_changed`) or exceptions are open
  (`exceptions_open`). A concurrent double-verify yields exactly one row.
- **AC-D.5** `[BE]` GIVEN a code with open `ProductSpecException` rows WHEN verify is attempted
  THEN it is refused and the pane surfaces the exceptions inline (D8).
- **AC-D.17** `[BE]` GIVEN a flagged spec key WHEN a user sets that key's value by hand THEN the
  exception is **answered and does not come back** on the next derivation. There is **no resolve
  action, no dismissal, and no reason field**: the user is the authority on their own catalogue,
  so correcting the value IS the resolution and no justification is required of them.
  Implemented by filtering `result.exceptions` at the rebuild in `derive_for_code` - where
  provenance is already in hand - to drop any flag whose `spec_key` carries a value from
  `AUTHORED_SOURCES`. The existing delete-and-reinsert rebuild is **kept**: it is what makes a
  corrected fact stop being flagged, with nothing to carry forward.
- **AC-D.17b** `[BE]` GIVEN a key a user has answered WHEN the underlying data later changes so
  the rules disagree with the authored value THEN the disagreement surfaces as
  `human_override_conflict` (D8, AC-F.5), not as the original flag. An answered question does not
  re-ask itself; a new question gets asked once.
- **AC-D.17c** `[FE]` GIVEN an open exception WHEN it renders THEN it names the key it is about
  and offers the edit for that key **in place**, so answering it is one action on the row rather
  than a trip to another screen. GIVEN the measured baseline (M7) THEN every one of the 258
  blocked codes is answerable this way, because every flagged key is a spec key: `shape` (212),
  `diameter` (25), `dim_*` (16) and `brand` (5).
- **AC-D.6** `[BE]` GIVEN the worklist WHEN it is served THEN discontinued codes are **excluded by
  default** with an include toggle, cutting the list from 11,415 to **8,812** (M6), and the
  progress line counts the same set it lists. Default order is needs-re-verify first, then
  unverified **grouped by class then code**.
- **AC-D.7** `[BE]` GIVEN coverage WHEN it is computed THEN it is computed **inline in the
  worklist SQL** against the 52-row registry, not by calling `keys-for-product` per code - that
  endpoint returns the numerator, is one query per code, and sits behind a zero-grant permission.
  Measured cost of inline coverage is nil (M9). Coverage is a displayed column and an explicit
  sort, **not** the default order: with a median of 4 keys against a denominator of 45-52 (M8),
  "worst coverage first" degenerates to ascending key count and sends the reviewer to the
  emptiest, slowest products first.
- **AC-D.8** `[FE]` GIVEN the verification screen WHEN it renders THEN it is the **shared
  `DataGrid` list component used exactly as the user list uses it** (D5): server-paginated,
  searchable, filterable, with `tableLayout: {width:'fixed', columnsResizable:true}`, explicit
  `size` per column and truncate + title on long text. No split pane, and no client-side
  virtualized list - the repo has no virtualization library and never loads thousands of rows
  client-side.
- **AC-D.9** `[FE]` GIVEN a row WHEN it renders THEN it carries enough to judge the product
  without opening it: code, class, brand, coverage, open-exception count and the verification
  pill. Seeing many products at once is the point of the screen.
- **AC-D.10** `[FE]` GIVEN the grid WHEN it renders THEN it has the **standard select-all at the
  top left**, matching every other listing, plus per-row checkboxes. Selection is **page-scoped**,
  which is what the shared component already does (`toggleAllPageRowsSelected`). The optional
  cross-page `selectAllMatching` banner is **not** wired: without it a bulk stamp can only cover
  rows the user actually had on screen. Enabling whole-filter selection is a deliberate decision
  and would need to be taken explicitly.
- **AC-D.11** `[FE][BE]` GIVEN selected rows WHEN **Verify selected** is pressed THEN a
  confirmation states the count (per the bulk-action copy standard) and one bulk call stamps them.
  The response is **per-code, not all-or-nothing**: codes that cannot be verified are reported
  with their reason rather than failing the batch, and the result is surfaced as
  "42 verified, 3 skipped - exceptions open, 1 skipped - changed while you were reviewing".
  Anything skipped stays selected so it can be dealt with.
- **AC-D.12** `[FE]` GIVEN a product row WHEN it is clicked THEN it opens **the existing product
  detail page on its Specifications tab**. There is **no new detail route**: the editable table,
  the exceptions and the diff all already live there, and that page already carries prev/next
  record navigation, so reviewing one by one costs no extra build.
- **AC-D.13** `[FE]` GIVEN the Specifications tab WHEN it renders for a code in the worklist THEN
  it carries the single-product **Verify** action, the verification pill with who and when, and
  for a needs-re-verify code the `invalidated_diff` as was/now pairs.
- **AC-D.14** `[FE][BE]` GIVEN a product detail page WHEN its Specifications tab renders THEN the
  verification block comes from the **existing** `by-product/{id}` response, not a second round
  trip, and both company copies of a code show the identical badge.
- **AC-D.15** `[BE]` GIVEN the new routes WHEN they are gated THEN they reuse
  `master_data.products.view` (worklist) and `.edit` (verify, bulk verify, resolve). **No new
  permission slug is minted**: a dedicated slug would ship the feature 403'd to everyone, which is
  exactly what happened to the spec registry (M1). Restricting verification to a smaller group is
  a deliberate decision that must arrive with a seeded grant in the same migration.
- **AC-D.16** `[BE]` GIVEN the bulk verify endpoint WHEN it stamps a code THEN it applies the
  **same guards as the single verify**: the values hash is compared in the same transaction and
  open exceptions still block. Bulk is a loop over the same rule, never a second, laxer path -
  otherwise the bulk button quietly becomes the way to stamp what the single button refuses.
- **AC-D.17b** `[FE]` GIVEN the filters WHEN they are set THEN they persist in the URL so a link
  is a shareable slice and a refresh resumes in place.
- **AC-D.18** `[FE]` GIVEN the new screen WHEN it is named THEN it is **not** called
  `SpecWorkbench` - that name is already taken by the master screen's tab shell.
- **AC-D.19** `[E2E]` GIVEN a user WHEN they navigate **by sidebar clicks from `/`** to Spec
  Verification THEN: they can filter, verify a single row **from its own row button**, then
  **unverify that same row** and see it read unverified again; tick several rows, press Verify
  selected, confirm the count, and see those rows flip state; a selected code with an open
  exception is reported as skipped with its reason rather than failing the batch; clicking a
  product lands on its Specifications tab where a single Verify works and prev/next moves to the
  next product; and an edit to a verified code returns it as needs-re-verify with the diff. Clean
  console, at **375px and 1280px**.

### B - Prompt box, extraction proposals, and the flyer discard (PR 4)

- **AC-B.1** `[FE]` GIVEN the Specifications tab WHEN it renders THEN the stored flyer card is
  replaced by a **prompt box**; the pasted text lives in component state and the request body only
  and is **never persisted**. A pytest asserts the flyer row count and the spec `updated_at` are
  unchanged across an extract call.
- **AC-B.2** `[BE]` GIVEN pasted text WHEN the extract endpoint is called THEN it returns
  **proposals only** and performs **no write**. It is gated on `master_data.products.edit`, not on
  any `spec_registry` permission (M1). Empty and over-length text are refused with readable
  messages rather than truncated.
- **AC-B.3** `[BE]` GIVEN a proposal WHEN its `kind` is decided THEN it is computed
  **server-side**, never in the FE, so milestone 2's supplier review uses byte-identical
  semantics. A proposal equal to the stored value after coercion is **omitted entirely**: a flyer
  restates most of what the description already produced, and fifteen rows of which two matter is
  a list nobody reads. A tombstoned key counts as a conflict.
- **AC-B.4** `[BE]` GIVEN extraction WHEN it runs THEN it uses a **sibling entry point** in
  `product_spec_understanding` sharing `_vocabulary` / `_coerce` / `_validated_pairs`, so it
  cannot invent vocabulary the ranker has never heard of, and it applies the same key scope gate
  derivation uses so an out-of-class key cannot be proposed. `understand_phrase` is **not**
  overloaded with a mode flag - it carries a WhatsApp latency budget this does not.
- **AC-B.5** `[BE]` GIVEN no model is reachable WHEN extraction runs THEN it degrades to the
  deterministic resolver and returns 200 marked as such, rather than failing the user with a 502.
- **AC-B.6** `[BE]` GIVEN the extraction prompt WHEN it is resolved THEN it comes from the DB
  prompt registry as its own `PROMPT_KEYS` entry declaring **zero variables** (so any `{{token}}`
  an editor types is rejected at save) with a mandatory hardcoded fallback.
- **AC-B.7** `[FE]` GIVEN proposals WHEN they render THEN each row is badged **New** / **Changes X
  to Y** / **Conflicts with your value X**, is independently checkable, and **conflict rows are
  unchecked by default**.
- **AC-B.8** `[FE]` GIVEN the proposal review UI WHEN it is written THEN it is a **shared
  component** taking `kind` as data, owning no product identity, supporting lifted selection, and
  importing no service - so milestone 2 reuses it for a multi-product supplier review (M2-S4).
- **AC-B.9** `[BE]` GIVEN accepted proposals WHEN they are applied THEN they write through **one
  batch call** over `apply_spec_values`, not one call per key: N calls would produce N fan-outs, N
  rendered-text rebuilds and N verification diffs for a single user action, and a partial failure
  would leave the table half-applied.
- **AC-B.10** `[BE][M]` GIVEN the promote migration WHEN it runs THEN every provenance entry with
  `source='flyer'` is re-stamped
  `{"source": "human", "evidence": "flyer: <original>", "migrated_from": "flyer"}` (D2). It is
  **idempotent and mismatch-based**, touches `provenance` **only**, and repairs a prior partial
  run rather than skipping it. A second run updates zero rows and a checksum over `values` is
  identical before and after. Blast radius stated in the PR: **3,353 entries, 1,389 rows, 695
  codes** (M2). The downgrade is written and exact.
- **AC-B.11** `[BE][M]` GIVEN the migration sequence WHEN it is executed THEN it runs strictly:
  (1) the source-keyed boost branch and `human_source_boost` [PR 1, verified present before this
  slice runs] -> (2) promote migration -> (3) derivation stops reading the flyer input -> (4)
  surfaces retire -> (5) `ProductFlyerText` drops. **Steps 2 and 3 ship in the same deploy.** The
  gap is one-directional data loss: step 3 before step 2 means the next `derive_for_code` on an
  affected code - fired by the change listener on any description edit, not just the nightly job -
  permanently drops every flyer-only value on that code.
- **AC-B.12** `[BE][FE]` GIVEN the findability sweep WHEN the promote migration runs THEN
  findability is retired in the **same deploy as step 2, not step 4**. Its selector filters on
  `source='flyer'`, which the promote empties, so it would keep rendering and quietly report a
  weaker test under the same numbers. Historical run rows stay readable; dropping those tables is
  a later cleanup.
- **AC-B.13** `[BE]` GIVEN the flyer input is removed WHEN the derived-input fingerprint changes
  THEN a **full-catalogue re-derive is scheduled as a deploy step** with before/after row and
  exception counts, because the fingerprint of all 11,415 codes changes and the next run rewrites
  all 22,805 rows.
- **AC-B.14** `[BE][FE]` GIVEN the retirements WHEN they land THEN the flyer-text endpoint and its
  response field, `FlyerCard`, the flyer service function, the bulk flyer importer, and the
  findability endpoints and panel go together, so no screen offers a setting that silently does
  nothing. The PR description lists the deleted tests explicitly.
- **AC-B.18** `[BE]` GIVEN derivation stops **reading** the flyer WHEN its text pass is retired
  as an input THEN the pass is **lifted, not deleted** (captain, 2026-08-14): the source-major
  flyer pass, the `source: 'flyer'` rule scope, and `_DESCRIPTION_FIRST_KEYS` survive inside a
  pure `propose_from_text(text, code)` that returns candidate key-values **with evidence** and
  **writes nothing**. `derive_for_code` already takes `flyer_text` as a parameter, so the seam
  exists. The "Flyer only" scope stays in the rule editor because rules scoped to flyer text now
  feed the proposal path. This preserves the extraction knowledge tuned to the real flyer for
  the bulk flyer-ingestion slice that follows PRs 1-4 (its own UAC/plan; evidence:
  `flyer-spec-ingestion/report.md` sections 5.2-5.3).
- **AC-B.15** `[FE]` GIVEN a promoted value WHEN it renders THEN it is badged so a user can tell
  why a value they never typed says "Set by hand" - the `migrated_from` marker survives for
  exactly this purpose.
- **AC-B.16** `[BE]` GIVEN a promoted value WHEN a future derivation rule would produce a
  different value THEN the promoted value stays in force and raises `human_override_conflict`
  (D8) rather than being updated. This is the intended consequence of promotion, not a defect,
  and it means `finish` (990 promoted entries) stops benefiting from rule work on those codes
  until someone resolves each flag.
- **AC-B.17** `[E2E]` GIVEN a user WHEN they navigate **by sidebar clicks from `/`** to a
  product's Specifications tab THEN they can paste a **real committed fixture**, get proposals,
  untick a conflict, apply, and see the table update - asserting the calls were extract then batch
  apply and that no flyer-text call exists any more. Clean console, at **375px and 1280px**.

### Milestone 2 seams (requirements of THIS milestone)

- **M2-S1** `AUTHORED_SOURCES` set, never `== 'human'`; `'supplier'` reserved now. -> AC-F.7
- **M2-S2** Party-scoped verification table; never a `verified_at` column pair on
  `ProductSpecifications`. -> AC-D.1
- **M2-S3** The spec cell/table component is props-driven with no `apiFetch` in the cells, and
  lives where the `(auth)`-group portal can import it. -> AC-A.12
- **M2-S4** The proposal-diff review component is shared, takes `kind` as data, and supports
  lifted selection for a multi-product review. -> AC-B.8
- **M2-S5** Value-diff invalidation is **party-agnostic** - a supplier acceptance invalidating a
  stale internal stamp falls out of the rule. Pinned by a pytest that inserts a supplier row by
  hand before the feature exists. -> AC-D.3
- **M2-S6** Applicability stays **code-driven and server-side**, so milestone 2's pre-seeding
  calls the same logic. Note the correction: the applicable-keys source is the new
  `applicable_keys_for_code`, not `keys-for-product`. -> AC-A.7
- **M2-S7** The pill vocabulary carries the verification states once, party-labelled at the call
  site, so milestone 2 adds **zero palette**. -> AC-C.1, AC-C.3
- **M2-S8** Pre-seeded blanks will live on the milestone 2 request object, **never in
  `product_specifications`**, so the tombstone shape and "awaiting fill" can never collide. The
  canonical hash drops null-valued keys, which enforces this from the foundations up. -> AC-F.11

## Tests (test-first - TDD, `PRINCIPLES.md` step 4; never deferred to Phase 3)

- **pytest:** the resurrection pin (AC-F.3), hash canonicality including the numeric and array
  traps (AC-F.11), fan-out (AC-F.4), conflict raised once per code and never for a tombstone
  (AC-F.5, F.6), the boost branch (AC-F.10), verification state derivation and party-agnostic
  invalidation (AC-D.2, D.3), the same-transaction 409 taxonomy (AC-D.4), exception resolve
  surviving re-derivation (AC-D.17), coverage per gate rule and worklist ordering/filters
  (AC-D.6, D.7), extraction writing nothing and dropping invented vocabulary (AC-B.1, B.4), batch
  apply atomicity (AC-B.9), and the promote migration run twice plus a prior-bad-run repair
  fixture and an exact downgrade (AC-B.10). **Bulk verify specifically:** a mixed batch returns
  per-code outcomes, a code with open exceptions is skipped rather than failing the batch, and a
  code whose hash moved is skipped with its own reason (AC-D.11, AC-D.16). **Unverify
  specifically:** a verified code becomes `unverified` and not `needs_reverify`; the original
  `verified_by`/`verified_at` survive on the row while `invalidated_by_*` is stamped; a
  needs-re-verify code unverifies to `unverified` with its diff cleared; unverifying a code with
  no history is a no-op, not an error; re-verifying after a withdrawal inserts a new row and
  leaves the withdrawn one intact; and an internal withdrawal leaves a `party='supplier'` row
  untouched (AC-D.20, D.21, D.26). Every route: happy + auth denial + validation. **Postgres
  only** (AC-F.14).
- **vitest:** every component's loading / empty / error / partial / data states; the cell renderer
  per data type; read-to-edit leaving DOM order unchanged (the same-layout mandate as an
  assertion); the tombstone row; the near-duplicate matcher; pill classes; the proposal badges and
  default-unchecked conflicts; the selection-to-bulk-action strip including the count in the
  confirmation copy and the partial-outcome summary.
- **playwright:** AC-A.16, AC-D.19, AC-B.17 - sidebar navigation only, asserting the expected
  `/api/v1/*` calls, at 375px and 1280px.

## Deferred

- The supplier portal and everything party-`supplier` -> **milestone 2**, its own UAC
  (`supplier-spec-portal`).
- "Most-searched first" worklist ordering - not buildable, no per-product search-hit log exists.
- A cleanup migration dropping the findability tables; rows stay read-only after the surfaces go.
- Converting the master spec list's hand-rolled table to `DataGrid` - pre-existing debt, separate
  ticket, deliberately outside this blast radius.
- The `product_spec` embedding queue having no producer - a **pre-existing defect**, filed as
  issue #139, explicitly not fixed here.
- New domain vocabulary introduced here (authored value, tombstone, values hash, party,
  needs-re-verify) has no glossary entry; `CONTEXT.md` covers no spec terms today. A follow-up
  should add them, and this PR deliberately touches no file outside
  `documentation/plans/master-data/`.
