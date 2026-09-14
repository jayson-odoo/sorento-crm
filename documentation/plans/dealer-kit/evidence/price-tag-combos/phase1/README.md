# Phase 1 browser evidence - price tag combos (S1, S2, S3)

Plan: `documentation/plans/dealer-kit/PLAN-price-tag-combos.md`
UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`

Walked with agent-browser 0.27.0 (headless, isolated session `ptagcombos`) against the
lane stack, frontend `:3083` / backend `:8083`, at 1280x900 and 375x812. Every surface
was reached by clicking from `/` through the sidebar, except the three noted under
"Deep URLs used, and why".

Everything below the service boundary is still the Phase 1 mock. What these shots prove
is that the UI, the states and the layering hold; what they cannot prove is persistence.

## Index

| Shot | Width | What it shows | AC |
| --- | --- | --- | --- |
| `s1-01-combos-empty-1280.png` | 1280 | Product overview tab carries Combos and Sold with; "No combos." plus the Add combo CTA | AC-S1-1 |
| `s1-02-duplicate-combo-name-1280.png` | 1280 | Second combo with the same name refused INLINE in the modal, not a toast | AC-S1-2 |
| `s1-03-combo-parts-choice-group-1280.png` | 1280 | Three parts: one fixed, then "Basin - pick one" with both basins under it | AC-S1-3, AC-S1-4 |
| `s1-04-sold-with-1280.png` | 1280 | The mirror's own page reads "SRTBF11834 · 3 in 1", linking to the host | AC-S1-6 |
| `s1-05-sold-with-375.png` | 375 | Same, stacked, no horizontal page scroll | AC-S1-9 |
| `s1-06-combo-parts-375.png` | 375 | Parts and the choice group at phone width, no page overflow | AC-S1-9 |
| `s1-07-deferred-delete-unknown-action-1280.png` | 1280 | The KNOWN Phase 1 gap: removing a part raises "Unknown action: 'product_combo_part.delete'" | AC-S1-5 (deferred) |
| `s2-01-parts-open-row-1280.png` | 1280 | Package "4 in 1" chosen, four fixed parts filled in, one open row "Not sure, any of 4" with "Marketing will prepare one tag per option" | AC-S2-1, AC-S2-2, AC-S2-3 |
| `s2-02-missing-part-warning-1280.png` | 1280 | A fixed part removed (staged, no countdown, no confirm) and the row warning reads "Missing: SRTMR502" | AC-S2-4, AC-S2-5 |
| `s2-03-parts-375.png` | 375 | Line and part rows at phone width, selects full width, no page overflow | AC-S2-11 |
| `s2-04-no-package-defined-1280.png` | 1280 | A guarded product with no package at all warns "No package defined" | AC-S2-5 |
| `s2-05-settings-guarded-classes-1280.png` | 1280 | System Settings "Price tag guarded classes" as a SearchableMultiSelect over the class labels, defaulting to Bathroom Furniture + Kitchen Sink | AC-S2-6 |
| `s3-01-lines-tab-nested-1280.png` | 1280 | CRM Lines tab: line row, indented part rows, then the tag row "1a / Open: Basin (4)" with List, Sell, Designed and Design | AC-S3-2 |
| `s3-02-rail-nested-open-1280.png` | 1280 | Designer rail: lines with tags nested under them, "Open: Basin" pill, "Split into 4 tags" and the four Pick one buttons | AC-S3-3, AC-S3-4 |
| `s3-03-rail-after-split-1280.png` | 1280 | After Split: 1a, 1b, 1c, 1d, each resolved to one candidate code, original id kept | AC-S3-4 |
| `s3-04-designer-deep-param-1280.png` | 1280 | `?tag=` selects that tag and the param is dropped from the URL | AC-S3-3 |
| `s3-05-designer-375.png` | 375 | The designer at phone width, no page overflow | - |
| `s3-06-lines-tab-375.png` | 375 | Lines tab at phone width: the table scrolls inside its own container, the page does not | AC-S3-2 |

## Walk log

**S1** Sidebar Products > Products > All Products, search `SRTBF11834`, open the row.
Overview tab renders Combos ("No combos." + Add combo) and Sold with ("This product is
not part of any combo."). Add combo -> name "3 in 1" -> created empty with its parts area
open. Add combo again with the same name -> inline "This product already has a combo
called "3 in 1"". Add part -> the shared product search (server-searched, `products` page
1 of the real catalogue) -> `SRTMR11406-WH`, then `SRTBS01` and `SRTBS01-NL`. Choice group
on `SRTBS01` typed as a new label via the create row ("Use "Basin""), on `SRTBS01-NL`
picked from the existing option -> the two render together under "Basin - pick one".
Back to list, open `SRTMR11406-WH` -> Sold with lists "SRTBF11834 · 3 in 1".

**S2** CRM contact row action "Impersonate in portal" -> portal as Jayson -> price tag
request form. Line 1 `SRTWT8267-GM` (mock bucket 3, two combos) -> Package select appears
with "2 in 1" / "4 in 1", no parts, row warning "No package chosen". Choose "4 in 1" ->
four fixed parts fill in plus one open row "Not sure, any of 4" / "Marketing will prepare
one tag per option" / "Basin"; the warning clears. Open row -> pick "Basin 800 grey" ->
becomes a product row. Remove `SRTMR502` -> gone on the click, warning becomes
"Missing: SRTMR502". Add part by hand -> `SRTMR11406-WH` appended. Line 2 `SRTMR11413`
(bucket 1) -> "No package defined".

**S3** Sidebar Dealer Kit > Room Designer > Price Tag Requests, open `PT-202609-0001`,
Lines tab -> per line: the line row, the fixed part rows, the open group row
`Basin: SRTBS801-WH / SRTBS801-BL / SRTBS801-GY / SRTBS801-MT`, then the tag row
`1a | Open: Basin (4) | 1 | RM 760.00 | - | Designed | Design`. "Designed" proves the
saved document's `request_line_id` was read through the S3 key rename. Design on 1a ->
the designer, `?tag=` consumed and dropped. Rail shows every line with its tags nested.
"Split into 4 tags" on 1a -> 1a/1b/1c/1d, each naming its own candidate. "Pick one"
(`SRTBS801-GY`) on 2a -> 2a resolves with no sibling. `?tag=<line 3 tag>` selects 3a;
`?line=<line 4 id>` selects 4a.

## Console

Clean on every surface except two entries, neither from this lane:

- `Each child in a list should have a unique "key" prop. Check the render method of
  `Demo1Layout`.` - the Metronic app shell, present before this work.
- `Missing `Description` or `aria-describedby` for {DialogContent}` - this WAS ours, from
  `AddComboModal`, and is fixed in the follow-up commit with an `sr-only`
  `DialogDescription` (the same shape `PromotionTypeFormModal` uses).

No uncaught page errors (`errors` empty) on any surface.

## Not verifiable in Phase 1

- **AC-S1-5 deferred delete.** The grace window is parked on the SERVER by design (D7),
  so removing a combo or a part raises "Unknown action: 'product_combo_part.delete'" until
  `app/services/record_actions.py` registers the two keys in Phase 2. Captain's ruling:
  no early registration. Shot `s1-07`.
- **AC-S2-9 draft round trip.** The backend does not yet store `combo_id` or the part
  rows, so a saved draft reopens without them.
- **AC-S2-10 `DUPLICATE_LINE`** and every other server rule: unchanged code path, Phase 2.
- **S4** (printed text and price) is server-fed and out of Phase 1 entirely.
- **`?line=` vs `?tag=` cannot be told apart** while the mock makes a line's base tag id
  equal the line id. Both resolve to the right tag (verified); which branch answered is
  covered by the vitest AC-S3-3 names.

## Deep URLs used, and why

The sidebar rule was followed for every surface under test. Three exceptions, none of
them the surface being verified:

- `/user-management/contacts` - the contacts list is not in the sidebar or the menu
  search (a pre-existing nav gap, unrelated to this lane). It was only the way to reach
  the portal impersonation action.
- `/portal/price_tag_request/new` - this contact's portal landing exposes only Stock
  Inquiry, so the price tag form has no link. A portal access-type configuration matter,
  not this lane's code.
- `/dealer-kit/price-tag-requests/{id}/design?tag=...` and `?line=...` - the deep params
  ARE the thing under test, and no UI emits `?line=` any more.

## A note on this folder

`documentation/agents/browser-verification.md` caps a lane at two screenshots. This set is
larger because the captain asked for the golden path and the edge cases at both widths.
Each file is well under the 200 KB the pre-push `png-size` gate enforces; trim it to the
two most load-bearing (`s3-01`, `s2-01`) if the standing cap is meant to win.
