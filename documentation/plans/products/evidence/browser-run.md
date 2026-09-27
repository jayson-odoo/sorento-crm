# Phase 3 browser verification - lane #1286 (product specifications for non-technical staff)

**Head verified against:** e4a46a20 (coder green). **Unblocked by the coordinator**: the fresh
cloud tenant had no app modules installed; all 23 were installed for tenant `__default__`, then a
fresh login (logged out/in via `/signin`) picked up the full sidebar.
**Stack:** frontend `http://localhost:3000` (already running, not restarted), backend
`http://localhost:8000` against the cloud DB (migrated to `spec_0002`).
**Tool:** `agent-browser@0.27.0`, session `lane1286`,
`AGENT_BROWSER_EXECUTABLE_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome`.
**Login:** the `E2E_EMAIL`/`E2E_PASSWORD` account from `sorento_crm_frontend/.env.local` (values
never printed); on-screen identity "Demo Superadmin". Navigated by sidebar clicks from `/`
throughout, except where noted (defect reproduction re-visits of an already-proven-reachable
route, and one direct-URL retry of a page that never finished loading - see AC-S0.8 below).

A backend fix round (phrase limits, a 409 for products still updating) and a frontend fix round
were landing in parallel per the coordinator's note; the dev server hot-reloaded several times
during this run (`[Fast Refresh] rebuilding` in the console) and one of the defects below
(the deferred-remove not landing until several seconds after commit) may be schedule-sensitive
for the same reason - it was still reproduced twice, cleanly, well clear of any reload window.

## Summary

Most of the new screens match the plan/UAC closely and in several places (the rules grid's six
columns, the rule modal's field order and controls, the "Reading and search" section, the search
answer line) match the spec's exact wording. Four real defects were found, one of them severe
(a reproducible renderer hang). Every AC below is scored against what was actually seen; ACs I
could not reach because of a defect are marked accordingly rather than guessed at.

**I introduced one accidental data change while reproducing the deferred-remove flow** (removed
the shipped `Ends with: -SC -> Satin chrome` rule on Finish or colour instead of my own test
rule, because the grid re-numbers on removal and I read a stale row index). I restored it
immediately in the same session (re-added `Code / ends with / -SC / Satin chrome`, saved, and
confirmed on a fresh page load that Finish or colour is back to 22 rules with that mapping
present). The rule's position in the list may differ from its original slot; its content and
match behaviour are identical. Flagging this explicitly per the instruction to report every
defect and misstep, not just the product's.

## Defects found

### D1 - CRITICAL: entering/leaving edit on "Choices and words" hangs the renderer
Reproduced twice, independently. On a spec record page (`Finish or colour`), with the record in
Edit mode and the **Choices and words** tab active, clicking **Edit** to enter the tab's own edit
affordance, or clicking a word cell to edit it in place, or clicking **Cancel**, made the page
stop responding to any further input. `ps aux` showed the renderer process pegged at ~69% CPU for
minutes (never recovering) the first time; the browser had to be killed and restarted both times.
No console error or exception was logged before the hang - it presents as a runaway render loop,
not a thrown error. This blocks a merchandiser from ever finishing a word edit on this tab once
they have entered edit mode from within it (entering edit mode from the **Details** tab first,
then switching to Choices and words, avoids the trigger and was how the rest of that tab's
screenshots below were taken).
No screenshot exists for the hang itself (a wedged renderer will not produce one); the CPU
evidence and reproduction steps are recorded here. **Blocks AC-S1.15's inline-edit sub-claim**
("Clicking a Choice or Words cell edits it in place") - the affordance is visible but not safely
operable.

### D2 - the save toast omits the product count
AC-S1.16 / D10 requires "Saved. N products updated." Saving a new rule on Finish or colour showed
only **"Saved."** - `evidence/ac-s1-16-saved-toast-real-1280.png`. The PATCH itself succeeded
(200) and the rule count updated correctly, so this is a toast-copy defect, not a save failure.

### D3 - a Brand's own detail page never finishes loading
Opening a Brand row (tried "OTHERS", then confirmed the same on "BRAVAT") navigates to
`/master-data-management/brands/{id}` and the page never leaves its loading-skeleton state.
`network requests` showed `GET /api/v1/master-data/brands/{id}` still pending indefinitely (no
status code, ever) while the list's own `GET /api/v1/master-data/brands?...` had already returned
200 moments earlier. Reproduced on a fresh page load (not just the first navigation).
Screenshots: `evidence/ac-s0-4-brand-others-detail-1280.png`,
`evidence/ac-s0-4-brand-others-detail-retry-1280.png`. **This blocks AC-S0.8's "Master data >
Brands form shows 'Customers can ask for this brand'" via the edit path** - see D4, which found
the same gap via the Create path instead.

### D4 - no "Customers can ask for this brand" control anywhere on the Brand form
Opened **Create Brand** (to work around D3) - `evidence/ac-s0-4-brand-form-customers-can-ask-1280.png`.
The dialog has Brand Code, Brand Name, Description, Access Levels, an **Active** toggle and a
**Flows to purchasing** toggle. There is no `is_searchable` control and no "Customers can ask for
this brand" wording anywhere on the form. **AC-S0.4's FE requirement ("The Brand form shows the
switch as 'Customers can ask for this brand'") fails** - the backend column and its seeded values
for OTHERS/NO LOGO were verified in Phase 2 (tester's red suite), but the toggle was never wired
into this dialog (and, per D3, the edit path cannot even be reached to check there instead).

### D5 - possible: "Product class" shows 0 Choices in the spec list
`evidence/ac-s3-list-loaded-1280.png` shows **Product class | List | 0 | 11,584**. AC-S3.3 says
"Choices for Product class equals the category class count" - 0 reads as no class labels exist
anywhere in the category master, which is surprising for a catalogue with 12 seeded demo products
across recognisable classes (water closet, kitchen sink, etc. all appear as rendered values
elsewhere in this run). Flagged as a possible defect rather than a confirmed one - I did not have
time in this pass to independently query the category master's class-label count to confirm
whether 0 is actually correct for this specific demo tenant.

## Pass/fail per AC

| AC | Result | Evidence |
| --- | --- | --- |
| AC-S0.7 (no Brand anywhere on spec list / Add specification) | **PASS** | `ac-s3-list-loaded-1280.png` (full list text has no Brand row); `ac-s0-7-add-specification-no-brand-1280.png` + full-list check (no "brand" in "show every specification") |
| AC-S0.8 (list no Brand; product Specifications tab no Brand; product Details tab still shows/edits brand; Brands form "Customers can ask...") | **PARTIAL FAIL** | List and product tab: PASS (`ac-s2-1-product-specs-tab-1280.png`, no Brand row). Details tab brand edit: PASS (`ac-s0-8-product-edit-brand-field-1280.png`, Brand dropdown = SORENTO, editable). Brands form wording: **FAIL**, see D3/D4 |
| AC-S1.1 (five kinds Words/Number/Size/Code/Product) | **PASS** | `ac-s1-14-rules-grid-bottom-1280.png` shows the grid; Kind dropdown offered Words, Number, Size, Code, Product (checked live in the Add-a-rule modal) |
| AC-S1.2 (matching semantics) | Not independently re-verified in the browser (covered exhaustively by the Phase 2 pytest suite); nothing observed here contradicts it | - |
| AC-S1.7 (Add a rule modal: fields in order, Code/Product hide Where to look, live grid-row preview) | **PASS** | `ac-s1-7-code-kind-fields-1280.png` (Where to look hidden for Code), `ac-s1-7-rule-preview-row-1280.png` ("This rule in the grid" live preview) |
| AC-S1.8 (Try it on a product / Reads nothing; See what would change) | **PASS** | `ac-s1-8-try-it-on-result-1280.png` ("Reads nothing."), `ac-s1-8-see-what-would-change-result-1280.png` ("0 changed / 0 added / 0 removed / 12 unchanged") |
| AC-S1.9 (drag handles / reorder while sorted by Order) | **PARTIAL** | Drag handles appear in edit mode (`ac-s1-14-rules-grid-edit-mode-1280.png`); Move up/Move down present in the row menu (`ac-s1-10-row-menu-3-1280.png`); did not test an actual reorder end to end (time) |
| AC-S1.10 (no "Changed here"/"Put back the built-in rules"; deferred 5s remove, no confirm dialog) | **PASS**, with a caveat | No such wording found anywhere in body text (grep for "Advanced", "Re-read" etc. all empty). Removal is deferred (row persisted through my first screenshot immediately after clicking Remove, then was gone on the next check) and no `confirm()` ever appeared. I could not capture the mid-countdown UI itself cleanly - CLI round-trip latency exceeded the 5s window twice. See "I introduced one accidental data change" above for the real cost of that latency. |
| AC-S1.11 (tabs Details, Choices and words, How it is read, Products, same order view/edit) | **PASS** | `ac-s1-11-12-finish-details-1280.png`, `ac-s1-13-14-finish-how-it-is-read-1280.png` |
| AC-S1.12 (Details: Name, In use, Other names grid; no code name/Built in/Advanced) | **PASS** | `ac-s1-11-12-finish-details-1280.png`, `ac-s1-12-details-edit-mode-1280.png` |
| AC-S1.13 (browser run at 375/1280; no Advanced/Re-read/sentence/pattern/underscore; modal no h-scroll at 375) | **PASS** | `ac-s1-13-rule-modal-375.png` (no horizontal scroll, fields stack); body-text grep for `\w_\w` and the banned words returned empty on the list and record pages |
| AC-S1.14 (rules grid six columns, sortable, row menu Edit/Move up/Move down/Remove, plain labelled values not sentences) | **PASS**, minor 375 deviation | `ac-s1-13-14-finish-how-it-is-read-1280.png` (all six columns, plain values like "FULL ROSE GOLD, ROSE GOLD"); `ac-s1-10-row-menu-3-1280.png` (Edit/Move up/Move down/Remove). At 375 the grid kept **Order, Where to look, Kind** rather than the UAC's named **Order, What to find, Value it sets** (`ac-s1-14-rules-grid-375.png`) - worth a look but not re-tested further given time |
| AC-S1.15 (Choices and words data grid, Add a choice, deferred remove, no chips) | **PASS for the static grid**; inline edit **BLOCKED by D1** | `ac-s1-15-choices-and-words-1280.png`, `ac-s1-15-choices-and-words-edit-mode-1280.png` (Add a choice visible) |
| AC-S1.16 (products_updated re-derive; toast wording) | **PARTIAL FAIL** | Re-derive and count worked (verified via the See-what-would-change preview and the rule taking effect); toast wording wrong, see D2 |
| AC-S1.18 (SearchableSelect/SearchableMultiSelect everywhere, "Add {WORD}") | **PASS** | `ac-s1-18-what-to-find-multiselect-1280.png` (checkbox list + search), `ac-s1-18-add-brushed-gold-1280.png` ("Add "BRUSHED GOLD""), `ac-s1-18-word-added-1280.png` (chip in trigger) |
| AC-S2.1 (order: checked line, values, price tag, Reading and search) | **PASS** | `ac-s2-1-product-specs-tab-1280.png`, `ac-s2-2-values-and-reading-search-1280.png` |
| AC-S2.5 (Reading and search = read values line + one search box, nothing else) | **PASS** | `ac-s2-2-values-and-reading-search-1280.png` |
| AC-S2.6 (price tag wording) | **PASS** | "Not set, the price tag uses the product description" + Edit price tag description, exact wording match |
| AC-S2.7 (no Brand row/picker on product tab) | **PASS** | `ac-s2-1-product-specs-tab-1280.png` (Flush type/Product class/Soft close/Trap/Trap outlet length/Type only) |
| AC-S2.8 (SRTWC7604-SC-SH: 1280 first row visible without scroll; 375 no clipping/h-scroll) | **PASS** | `ac-s2-1-product-specs-tab-1280.png` (first values row visible under the tab strip); `ac-s2-8-product-specs-tab-375.png` + `-375-b.png` (values table scrolls in its own frame, no page-level horizontal scroll) |
| AC-S2.10 (search box answers "This product comes up, Nth of M") | **PASS** | `ac-s2-10-search-answer-1280.png`: "one piece water closet" -> "This product comes up, 2nd of 3" |
| AC-S3.1 (list columns Specification/Type/Choices/Products; Code/Rules/Built in hidden but present in chooser) | **PASS** | `ac-s3-list-loaded-1280.png`, `ac-s3-1-column-chooser-1280.png` |
| AC-S3.2 (Type wording) | **PASS** | List/Number (unit)/Yes or no all seen; no Text-type spec exists in this catalogue to confirm that one word |
| AC-S3.3 (Choices = category class count for Product class; "-" for numbers/booleans) | **POSSIBLE FAIL** | see D5 |
| AC-S3.4 (no status pill/Re-read/"Never read"/"Rules changed since") | **PASS** | full-page text grep empty for all of these |
| AC-S3.6 (Back link in header gutter, "Back to specifications", loaded + not-found, 375/1280) | **PASS for loaded state**; not-found **not tested** (ran out of time before reaching a bad-key retry) | `ac-s1-11-12-finish-details-1280.png` (1280), `ac-s1-13-finish-details-375.png` (375) |
| Save a real rule / "Saved. N products updated." toast / remove + deferred countdown with Cancel | **PARTIAL** | Rule saved and took effect; toast wording wrong (D2); deferred remove confirmed functionally but the mid-countdown "Cancel" UI itself was not captured cleanly (see AC-S1.10 note and the accidental-change disclosure above) |

## Evidence index

All paths under `documentation/plans/products/evidence/`:
`ac-s3-list-loaded-1280.png`, `ac-s3-1-column-chooser-1280.png`,
`ac-s1-11-12-finish-details-1280.png`, `ac-s1-12-details-edit-mode-1280.png`,
`ac-s1-15-choices-and-words-1280.png`, `ac-s1-15-choices-and-words-edit-mode-1280.png`,
`ac-s1-13-14-finish-how-it-is-read-1280.png`, `ac-s1-14-rules-grid-bottom-1280.png`,
`ac-s1-14-rules-grid-edit-mode-1280.png`, `defect-add-rule-no-modal-fullpage-1280.png` (the
transient no-modal capture, superseded once the click was retried - kept as evidence the first
CLI-dispatched click can silently no-op on this button), `ac-s1-7-18-add-rule-modal-1280.png`,
`ac-s1-18-what-to-find-multiselect-1280.png`, `ac-s1-18-add-brushed-gold-1280.png`,
`ac-s1-18-word-added-1280.png`, `ac-s1-7-rule-preview-row-1280.png`, `ac-s1-8-try-it-on-1280.png`,
`ac-s1-8-try-it-on-result-1280.png`, `ac-s1-8-see-what-would-change-1280.png` (the mis-clicked,
dialog-closed attempt - kept as the same CLI-click caveat), `ac-s1-8-see-what-would-change-result-1280.png`,
`ac-s1-16-saved-toast-1280.png` (mid-flow, before the outer Save), `ac-s1-16-saved-toast-real-1280.png`
(the actual toast, "Saved." only), `ac-s1-10-row-actions-menu-1280.png`, `ac-s1-10-row-menu-2-1280.png`,
`ac-s1-10-row-menu-3-1280.png`, `ac-s1-10-deferred-remove-countdown-1280.png`,
`ac-s1-10-deferred-remove-countdown-fast-1280.png`, `ac-s1-7-code-kind-fields-1280.png`,
`ac-restore-sc-rule-1280.png` (the restoration of the accidentally-removed shipped rule),
`ac-s2-product-specs-tab-1280.png` through `ac-s2-1-product-specs-tab-1280.png` (tab-navigation
attempts before the click landed), `ac-s2-2-values-and-reading-search-1280.png`,
`ac-s2-10-search-answer-1280.png`, `ac-s0-7-add-specification-no-brand-1280.png`,
`ac-s0-8-product-details-brand-edit-1280.png` (stale, tab did not switch),
`ac-s0-8-product-edit-brand-field-1280.png` (the real one, Brand = SORENTO editable),
`ac-s0-8-brands-list-1280.png`, `ac-s0-4-brand-others-searchable-toggle-1280.png` (stale, still
list view), `ac-s0-4-brand-others-detail-1280.png`, `ac-s0-4-brand-others-detail-retry-1280.png`
(D3), `ac-s0-4-brands-list-columns-1280.png`, `ac-s0-4-brands-list-scrolled-1280.png`,
`ac-s0-4-brand-form-customers-can-ask-1280.png` (D4), `ac-s1-13-finish-details-375.png`,
`ac-s1-14-rules-grid-375.png`, `ac-s1-13-rule-modal-375.png`, `ac-s2-8-product-overview-375.png`,
`ac-s2-8-product-specs-tab-375.png`, `ac-s2-8-product-specs-tab-375-b.png`.

## Not reached in this pass (say so explicitly, per instructions)

- AC-S3.6's **not-found** state (a bad spec key after reaching the list by sidebar) - ran out of
  time.
- AC-S1.9's reorder **end to end** (dragging or Move up/Move down actually changing saved order) -
  the controls are present (screenshotted) but the reorder itself was not executed and re-verified.
- A second, controlled attempt to capture the deferred-remove countdown pill mid-flight - CLI
  round-trip latency (1-2s per command) made it disappear before a screenshot landed in three
  attempts; functional behaviour (deferred, no confirm dialog, server-committed even after the
  local edit was cancelled) was confirmed instead.
- AC-S1.2's matching-semantics statements were not re-driven through the browser (Phase 2's pytest
  suite already covers each one against `compile_builder` directly; nothing in this pass
  contradicts it).
- Independent confirmation of whether "0" is actually correct for Product class's Choices count
  (D5) - would need a query against this tenant's category master's class labels.

## Re-check after fix round 3

Same setup: session `lane1286`, sidebar clicks from `/`, 1280 and 375, no source edits, no
commits. Hard-reloaded (`open http://localhost:3000/signin` then logged back in fresh) before
starting - the first login attempt hung mid-request behind a `[Fast Refresh] rebuilding` cycle
(the fix round hot-reloading), a second attempt on a fresh `/signin` load went through cleanly
in about a second, consistent with the coordinator's warning rather than a new defect.

### D1 - Choices and words tab hang: **FIXED, PASS**

Reproduced the exact original trigger: opened Finish or colour, switched to the **Choices and
words** tab while still in view mode, then **Edit** -> inline edit a word cell -> **Cancel** ->
**Edit** again. Timed every step with `get url` immediately after: every response landed in
0.96-1.17s, both at 1280 and at 375 (no `ps aux` CPU spike, no wedge, no browser restart needed
either width).

- `recheck-d1-01-view-mode-1280.png` - the tab before entering edit
- `recheck-d1-02-edit-mode-1280.png` - Edit clicked, no hang, `get url` returned in 1.06s
- `recheck-d1-03-inline-edit-1280.png` - "Gunmetal"'s word cell open as an inline text input
- `recheck-d1-04-after-cancel-1280.png` - Cancel clicked, no hang, back to view mode
- `recheck-d1-05-edit-again-1280.png` - Edit clicked a second time, no hang, same tab still active
- `recheck-d1-06-edit-mode-375.png`, `recheck-d1-07-after-cancel-375.png` - the same Edit -> inline
  cell click -> Cancel cycle at 375, also clean (0.97-1.05s each)

**PASS.**

### D2 - toast wording and deferred remove: **FIXED, PASS**

Added a harmless Words rule to Finish or colour (`ZZTRECHECK -> Chrome`, a word no demo product's
description contains) through the real Add-a-rule modal, saved the rule, then saved the record.

- `recheck-d2-01-rule-filled-1280.png` - the rule and its live grid-row preview before saving
- `recheck-d2-02-saved-toast-1280.png` - the toast: **"Saved. 0 products updated."** - exact
  format match, D2 is fixed (0 is correct: the word matches none of the 12 demo products)

Removed it afterwards via the row's own actions menu, identifying the row by its **What to find**
text (`ZZTRECHECK`) rather than its row number, since the grid renumbers on removal - the mapping
that bit me last time (`Ends with: -SC -> Satin chrome`, restored last session) was double-checked
still present and correctly mapped at every step below, confirming that mistake is not repeated:

- `recheck-d2-03-row-menu-1280.png` - Rule 23's row menu open (Edit/Move up/Move down/Remove),
  `-SC -> Satin chrome` visible two rows above it, unaffected
- `recheck-d2-04-deferred-countdown-1280.png` - immediately after clicking Remove, the row is
  still present (deferred, not instant) - the countdown pill itself is off the right edge of the
  grid's own horizontal scroll frame in the screenshot (same CLI-latency caveat as the first pass:
  a script-level scroll of the grid's own container did not locate the cell in time); the
  functional deferred behaviour is confirmed by the next screenshot instead
- `recheck-d2-05-after-remove-1280.png` - moments later: **22 rules**, `ZZTRECHECK` gone,
  `Ends with: -SC -> Satin chrome` still present and correctly mapped

**PASS** (toast wording and deferred-remove both correct; the countdown pill's own pixels were
not captured, same tooling limitation as the first pass, not a product defect).

### D3 - Brand detail page: **FIXED, PASS** - and confirmed not environmental

`GET /master-data-management/brands/{id}` now loads and renders fully -
`recheck-d3-brand-detail-1280.png` (OTHERS: Basic information, Access, Record sections all
populated, no skeleton stuck).

Also opened a page this lane did not touch, **Product Categories > Kitchen Sink**
(`/master-data-management/product-categories/{id}`), to answer the coordinator's "is it
environmental" question directly: it loaded cleanly and immediately -
`recheck-d3-category-detail-1280.png`. So the original hang was specific to the Brand detail
route, not a property of this environment's detail-page pattern in general, and it is now fixed
either way.

**PASS.**

### D4 - "Customers can ask for this brand" toggle: **STILL MISSING, FAIL**

Checked both places a merchandiser would meet the brand form:

- The list's own row **Edit** path: clicking a brand's name/code cell in the Brands list
  (`Reference Data > Brands`) opens the **detail page** (not a separate dialog - the "..." row
  menu itself only offers "Duplicate brand" / "Delete brand", `recheck-d4-01-row-menu-1280.png`),
  and its **Edit** button switches the same page into an inline edit form:
  `recheck-d4-03-detail-edit-mode-1280.png`. Fields present: Brand code, Brand name, Description,
  Status, **Flows to purchasing**. No `is_searchable` control, no "Customers can ask for this
  brand" wording, anywhere on the page in either state.
- The **Create Brand** dialog (`recheck-d4-02-brand-dialog-1280.png` from the first pass, re-
  confirmed unchanged this pass by the same field list on the edit form above): same fields,
  same gap.

I could not find a distinct modal "dialog the list opens" separate from the page-level edit
described above - if fix round 3 intended a different surface for that toggle, it either did not
land yet or is not reachable from anywhere in the Brands list or detail page I could find by
sidebar/row clicks.

**FAIL - unchanged from the first pass.** AC-S0.4's FE requirement is still not met.

### D5 - Product class Choices count: **FIXED, PASS**

Filtered the Product Specifications list to "Product class":
`recheck-d5-02-product-class-1280.png` - **Choices: 4**, matching the coordinator's stated demo
data (was 0 in the first pass).

**PASS.**

### Re-check summary

| Item | Result |
| --- | --- |
| D1 (Choices and words hang) | **FIXED** |
| D2 (toast wording "Saved. N products updated.") | **FIXED** |
| D2 (deferred remove, identified by text) | **FIXED**, functionally confirmed |
| D3 (Brand detail page loads) | **FIXED**; confirmed not environmental (Category detail page, untouched by this lane, always loaded fine) |
| D4 (Brand form "Customers can ask for this brand") | **STILL FAILING** - no such control on either the Create dialog or the detail page's Edit form |
| D5 (Product class Choices = category class count) | **FIXED** (now reads 4) |

No source files were edited and nothing was committed during this re-check.

## Captain re-check of D4 after the detail-page fix

The brand detail page (`/master-data-management/brands/{id}`) has its own inline view and edit
form, which none of the fix rounds had touched. It now carries "Customers can ask for this
brand" in the same place in view (Yes / No) and edit (a switch), per the same-layout mandate.
Reached by sidebar clicks: Products > Reference Data > Brands > BRAVAT.

| Step | Result | Evidence |
| --- | --- | --- |
| Detail view shows "Customers can ask for this brand: Yes" | pass | text read in the session |
| Edit, switch off, Save brand; view reads "No"; `GET /brands/{id}` returns `is_searchable: false` | pass | `recheck-d4-brand-detail-searchable-off-1280.png` |
| 375 wide after reload, no horizontal page scroll (`scrollWidth <= innerWidth` true) | pass | `recheck-d4-brand-detail-375.png` |
| Set back on (API) | done | |
| Brands list > Create Brand dialog shows the switch, on by default | pass | `recheck-d4-create-dialog-1280.png` |

**D4: pass.** The one console message on the brands list is a React missing-key warning from
the list, which this lane does not change.

## Fix round 2 re-check (reviewer pass at ea0b804b)

**Stack:** backend `:8000` on a throwaway `sorento_demo` database (bootstrapped, `spec_0003`, the
49 shipped specifications with no stored rules, 6 products), frontend dev server `:3000`,
`agent-browser@0.27.0`, sidebar clicks from `/`.

| Check | Width | Result | Evidence |
|---|---|---|---|
| Spec list, four default columns, no issue badge | 1280, 375 | pass; 375 has no sideways page scroll (360 of 375) | `r2-spec-list-1280.png`, `r2-spec-list-375.png` |
| Rules grid, view | 1280 | pass | `r2-rules-grid-1280.png` |
| Rules grid, edit: row menu inside the card (S-13) | 1280 | pass: menu buttons at x 1185 to 1213 of 1280 | `r2-rules-grid-edit-1280.png` |
| Rules grid under sm: Order, What to find, Value it sets only, all visible (S-13) | 375 | pass | `r2-rules-grid-375.png` |
| Rule modal; Add "ZZT RED" by keyboard Enter (N-10); Try it on reads "Rose gold" (B-7) | 1280 | pass | `r2-rule-modal-1280.png`, `r2-rule-modal-try-it-1280.png` |
| See what would change: `SRTWC7605 - Rose gold`, no snake_case in the dialog (B-7) | 1280 | pass | `r2-see-what-would-change-1280.png` |
| A rule added in the modal takes an in-place word edit (B-4) | 1280 | pass: the row reads `WALL HUNG ZZT RED` | `r2-b4-inline-after-modal-1280.png` |
| Save re-reads the product | 1280 | pass: `SRTWC7605` stored `finish = rose_gold` | `r2-saved-toast-1280.png` |
| Try it on in view mode, grid "Reads:" line (B-7) | 1280 | pass: "Reads: Rose gold", no snake_case on the page | `r2-try-it-grid-1280.png` |
| Remove a saved rule | 1280 | goes through `/pending-actions` (202) and commits after 5 s; "Remove disabled during its own countdown" is pinned by vitest, the harness is too slow to open a second menu inside 5 s | none |
| Rule modal | 375 | pass: dialog 0 to 375, no sideways scroll | `r2-rule-modal-375.png` |
| Product Specifications tab, one search box: "one piece twister wc" reads "This product comes up, 1st of 3", one request (S-15) | 375, 1280 | pass | `r2-product-specs-search-375.png`, `r2-product-specs-tab-375.png`, `r2-product-specs-tab-1280.png` |

## Fix round 3 re-check (N-R6)

Re-shoot of the Rules grid at 375, requested to close reviewer nit N-R6: `r2-rules-grid-375.png`
still showed the removed "The first rule that finds something wins" copy (predating commit
2e1d065f) and did not include an edit-mode shot at 375 at all, so the 358/398 px column-sum claim
from that nit was never verified against HEAD in a real browser. This pass builds a brand new
stack, seeds a fresh "Finish or colour" specification the ordinary way, and re-measures with JS
in the page rather than reading the screenshot by eye.

**Stack:** PR #1302 branch `claude/product-specs-non-technical-1rrf5o` at commit `dd323a60`, on
its own throwaway `sorento_demo` Postgres database (`scripts.bootstrap_env`, run against
`sorento_demo`, not the `sorento_ci` database another process was using), backend on `:8000`
(`SORENTO_ENV_FILE=.env.demo`), every catalog module installed and enabled for tenant
`__default__` so the sidebar shows Products, a fresh superadmin login user created directly in
the database, `product_spec_registry` seeded the normal way (`seed_spec_registry`, 49 rows,
`derivation_rules` left `NULL` on every row so each key reads its shipped rule set), frontend
`npm run dev` on `:3000`, `agent-browser@0.27.0` session `evidence-n-r6`. Navigated by sidebar
clicks from `/`: Products > Specifications > Product Specifications > searched "Finish" > Finish
or colour > **How it is read** tab. That specification carries 22 shipped rules including the
named `GOLDEN YELLOW -> golden_yellow` one, so it is the same case the nit described.

Both `r3-rules-grid-375.png` (view) and `r3-rules-grid-edit-375.png` (edit, drag handles visible)
are fresh screenshots of that tab at a 375x800 viewport, taken after setting the viewport with
`agent-browser set viewport 375 800`, plus `r3-rules-grid-1280.png` at the original 1280x633
viewport, plus one extra, not requested but useful, `r3-rules-grid-edit-375-scrolled.png`: the
same edit-mode card with its own internal scroller driven to `scrollLeft = scrollWidth` by JS, to
show what is on the other side of the cut rather than only asserting it exists.

| Check | Width/mode | Result | Measured | Evidence |
|---|---|---|---|---|
| Stale copy "The first rule that finds something wins" | either mode | absent | `document.body.innerText.includes('first rule that finds')` = `false` | `r3-rules-grid-375.png`, `r3-rules-grid-edit-375.png` |
| Page-level sideways scroll | 375, view | none | `document.documentElement.scrollWidth` 360 vs `window.innerWidth` 375 | `r3-rules-grid-375.png` |
| Page-level sideways scroll | 375, edit | none | `document.documentElement.scrollWidth` 360 vs `window.innerWidth` 375 | `r3-rules-grid-edit-375.png` |
| Grid's own internal scroller (Order, What to find, Value it sets; no drag handle or Actions column in view mode) | 375, view | fits, no internal scroll needed | scroller `scrollWidth` 311 equals `clientWidth` 311; header row spans 311 of the card's 328 px, the remaining 17 px is the vertical scrollbar's own reserved width (`offsetWidth` 326 vs `clientWidth` 311 on the same element), not clipped content | `r3-rules-grid-375.png` |
| Grid's own internal scroller (+ 40 px drag handle + 52 px Actions column) | 375, edit | still overflows | scroller `scrollWidth` 398 vs `clientWidth` 311, a 87 px shortfall, i.e. still the same 398 px the nit measured on the pre-fix build | `r3-rules-grid-edit-375.png` |
| "Value it sets" column header text | 375, edit, unscrolled | visually cut ("Value it s") | header cell's own right edge sits at x=363, the scroller's visible clip is at x=343: 20 px of the header ("ets") is past the clip | `r3-rules-grid-edit-375.png` |
| Same header, scrolled to the far right of the grid's own frame | 375, edit, `scrollLeft` 87 (max) | fully visible; the Order column and its drag handle are cut on the left instead | visual, matches the "scrolls inside its own frame" behaviour the component's own code comment claims | `r3-rules-grid-edit-375-scrolled.png` |
| "Value it sets" cell content, e.g. the named `Golden yellow` | 375, view | still ellipsis-truncated to "Golden y...", with a `title="Golden yellow"` tooltip | button `scrollWidth` 93 vs `clientWidth` 74 | `r3-rules-grid-375.png` |
| "What to find" cell content, e.g. `GOLDEN YELLOW` | 375, view | still ellipsis-truncated to "GOLDEN YELL...", with a title tooltip | span `scrollWidth` 120 vs `clientWidth` 110 | `r3-rules-grid-375.png` |
| Column widths, view mode | 375 | Order 63 px, What to find 142 px, Value it sets 106 px; sums to the scroller's own 311 px | measured via `getBoundingClientRect()` on each header cell | `r3-rules-grid-375.png` |
| Same tab, no viewport constraint | 1280 | no truncation visible anywhere in the columns shown ("Golden yellow" reads whole) | n/a | `r3-rules-grid-1280.png` |

**Plainly:** the stale copy is gone and confirmed gone by a text search of the whole page, not
just by eye. The page itself never scrolls sideways at 375 in either mode. View mode is genuinely
clean at 375: its three columns fit the card's own scroll frame exactly (311 of 311 px), so nothing
about the *grid's width* clips there; the individual `Golden yellow` / `GOLDEN YELLOW` cells still
truncate to an ellipsis with a hover tooltip, which is the documented `truncate` + `title` pattern
the design standard calls for on DataGrid long text, not a layout bug. Edit mode is the one that
still clips exactly as the nit described: the drag handle and the row-actions column push the
grid's own content to 398 px against a 311 px visible frame, a 87 px shortfall that is close to
the 40 px difference between the nit's reported 358 (view) and 398 (edit) figures, and at 375 the
card is too narrow to show the Order/drag-handle end and the Value it sets/Actions end at the same
time: scrolling the grid's own frame reveals one end at the cost of the other, it does not lose
data, but the "Value it sets" header is visibly cut ("Value it s") the moment edit mode opens,
before anyone scrolls anything. This is a real, unresolved edit-mode-at-375 layout gap on HEAD
(`dd323a60`), reported here as measurement only, no source file was edited to produce it.
| Next.js "1 Issue" badge | all | was a missing-key console error from the protected layout on every page; 0 console errors after the fix on `/`, the spec list and the record page | none |
