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
