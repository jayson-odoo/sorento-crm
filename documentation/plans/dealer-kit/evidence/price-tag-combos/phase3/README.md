# Phase 3 browser evidence - price tag combos

Walked 14-15 Sep 2026 against the RUNNING lane stack (FE `http://localhost:3083`,
BE `:8083`), code `feat/price-tag-combos` at `a30927e61`. agent-browser 0.27.0,
headless, isolated session `ptagc-verify`, closed by name at the end.

UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`.
Plan: `documentation/plans/dealer-kit/PLAN-price-tag-combos.md`.

Screenshots (the policy cap is two per lane):

- `portal-parts-375.png` - portal request form at 375, the cabinet's package
  filled in with a fixed part row and an open Basin row.
- `split-line-pdf-two-tiles.png` - the tag sheet print page for PT-202609-0009
  (AC-S4-4), swapped in for the CRM Lines tab shot to stay inside the cap; the
  Lines tab is covered in prose under "Result" and by
  `PriceTagRequestDetail.test.tsx`.

## How the walk was navigated

Sidebar clicks from `/` throughout, per policy. Two deliberate exceptions, both
setup rather than the feature under test, both recorded here:

- `/user-management/contacts` was opened by URL. It has NO sidebar entry in this
  build (checked: Users & Access > People holds Administrative Users, Internal
  Users, Teams, Sales Agents, Onboarding Requests; Access holds Roles,
  Permissions, AI Agents, Contact Access Types). It was needed only to reach the
  contact's Portal link.
- The portal was entered by writing the CRM's own impersonation token into
  `sessionStorage['sorento.portalToken']`, which is exactly what the CRM's
  impersonate action does (`portal-client.ts` `writePortalToken`). The token was
  a live, server-verified `is_impersonation` row; the portal's OTP gate was not
  bypassed in the backend. The "Exit Impersonation" banner confirmed the
  session.
- `?line=<lineId>` was opened by URL on purpose - it IS the legacy deep link
  AC-S3-3 asks about, reached after the designer had already been opened the
  normal way.

Price tag requests live at **Dealer Kit > Room Designer > Price Tag Requests**,
reached by sidebar click and confirmed rendering.

## Result

| AC | Verdict | Evidence |
| --- | --- | --- |
| AC-S1-1 | PASS | Product SRTBF11834 overview tab shows "Combos" with "3 in 1" and its parts (code, name, dimensions). A product with none (SRTBS01) shows "No combos." plus an Add combo button. Loading and error states are separate from the empty state. |
| AC-S1-2 | PASS | Add combo asks for a name only and creates it EMPTY ("No parts yet."). A second "3 in 1" on the same host: `POST /master-data/products/{id}/combos` -> **409**, message rendered INLINE in the modal: `This product already has a combo called "3 in 1"`. A different name ("4 in 1") succeeded. |
| AC-S1-3 | PASS | Add part opens the shared server-searched product picker. Host as part -> `POST .../combos/{id}/parts` **422**, inline `A product cannot be a part of its own combo`. Already-present part -> **422**, inline `That product is already on this combo`. A real part (SRTTT834) added and rendered with `800 x 500 x 60 mm`. |
| AC-S1-4 | PASS | Every part row carries a clearable choice-group control (placeholder "Fixed part", "Clear selection" on a set one). The two basins render together under `Basin - pick one`; the fixed mirror is outside that block. A group of one shows the label without "pick one". |
| AC-S1-5 | PASS | Remove part produced a countdown toast `Removing in 3s / Cancel / SRTTT834 from 3 in 1` - no `alertdialog`, no confirm. The countdown was left to LAPSE: the part was gone afterwards and `GET /pending-actions/current?entity_type=product_combo_part` was polled throughout, so the commit was server-parked. |
| AC-S1-6 | PASS | On the PART's own page (SRTBS01) "Sold with" reads `SRTBF11834 · 3 in 1`, linking to `/master-data-management/products/82f32959-...` (the host). Its own Combos section correctly says "No combos.". |
| AC-S1-7 | NOT BROWSER-VERIFIABLE | Company scoping is a server rule; this walk had one company's session. Covered by `tests/test_product_combos.py::test_combos_cross_company_404`. |
| AC-S1-8 | NOT BROWSER-VERIFIABLE | Chatbot resolver behaviour, no UI. Covered by `tests/test_product_combos.py::test_business_gate_ignores_combos`. |
| AC-S1-9 | PASS | At 375x812 on the product page: `documentElement.scrollWidth == clientWidth == 360`, no page overflow; the Combos card measured 328 wide inside it and did not overflow itself. |
| AC-S2-1 | PASS | Picking SRTBF11834 fired `GET /api/v1/public/portal/lookups/product-combos/82f32959-...` **200** and filled the package in: the fixed mirror as a product row, and ONE open row for the group - `Not sure, any of 2` + `Marketing will prepare one tag per option` + the label `Basin`. The two basins are NOT listed as two parts. |
| AC-S2-2 | PASS | After a second combo was added to the host, the same pick showed a clearable "Package" select listing `3 in 1` and `4 in 1` with NO parts filled in. Choosing "4 in 1" filled SRTTT834; switching to "3 in 1" replaced it with the mirror + the open Basin row. |
| AC-S2-3 | PASS | The open row's select offered `SRTBS01` / `SRTBS01-NL`. Choosing one turned the row into a product row and removed the copy line; "Clear selection" reopened it with both candidates and the copy back. |
| AC-S2-4 | PASS | Remove on a part row took it away immediately - no dialog, no countdown toast (staged removal). A part was then re-added by hand through the shared catalogue search on the same line. |
| AC-S2-5 | PASS | Client-side, before submit: removing the mirror raised `Package warning / Missing: SRTMR11406-WH` on the row, and re-adding it cleared the pill. With two combos and none chosen: `Package warning / No package chosen`. Server-side on a clean submitted line (PT-202609-0011): `package_warning` stored NULL. |
| AC-S2-6 | NOT WALKED | System Settings multi-select over `class_label` was not exercised in this session; the guard demonstrably reads a guarded class (Bathroom Furniture warned, the flow behaved). Covered by `tests/test_price_tag_package_warning.py::test_settings_guarded_classes_round_trip` and `::test_the_guard_reads_the_setting_not_a_hardcoded_list`. |
| AC-S2-8 | PASS | PT-202609-0011 stored: `combo_id` not null, 2 part rows, 1 tag. Parts persisted through submit in the order the form held them. |
| AC-S2-9 | PASS | Save Draft created PT-202609-0010; reopening it showed the open Basin row (still open, both candidates, copy intact) and the hand-added mirror part. |
| AC-S2-10 | NOT WALKED | Duplicate-line refusal is unchanged by this slice; covered by `tests/test_price_tag_package_warning.py::test_duplicate_line_still_refused`. |
| AC-S2-11 | PASS (with note) | At 375x812 the portal form did NOT scroll the page horizontally (`scrollWidth == clientWidth == 375`). The lines TABLE scrolls inside its own container (measured 560 wide) - that is r7's existing lines-table pattern, not introduced here. The open-row and package selects measured 502 wide, i.e. full row width. |
| AC-S3-1 | PASS | Submitting PT-202609-0011 created exactly one tag for its line, carrying the line's quantity. |
| AC-S3-2 | PASS | CRM Lines tab, PT-202609-0009: line row (Product / SRTBF11834 / Qty 1), then part rows `SRTMR11406-WH - SRTMR11406-WH` and `Basin: SRTBS01 / SRTBS01-NL`, then tag rows `1a SRTBS01` and `1b SRTBS01-NL` with price and a Design action each. On an unsplit line the tag row reads `1a | Open: Basin (2)`. |
| AC-S3-3 | PASS | The designer rail lists the line once with its tags nested (`1a`, `1b`), each with its own resolved code and price. `?tag=` opened the named tag (1a selected) and the param was dropped from the URL. `?line=<id>` resolved to that line's FIRST tag and was likewise dropped. |
| AC-S3-4 | PASS with DEFECT D1 | An open tag shows `Open: Basin`, a `Split into 2 tags` button and a `Pick one` select (the select lists the candidate CODES). "Pick one" -> `PATCH .../tags/{id}` **200**, stored `choices = {"Basin": "<product id>"}`, no sibling added. "Split into 2 tags" -> `POST .../tags/{id}/split` **200**, two tags 1a/1b resolved to the two candidates, original id kept. **But the prices shown afterwards are stale - see D1.** |
| AC-S3-5 | PASS (route), NO UI | The per-tag route round-trips: "Pick one" writes through `PATCH /price-tag-requests/{id}/tags/{tag_id}`. No override editor exists in the designer or the Lines tab at this HEAD; the UAC marks this AC `[BE]`, and the Lines tab renders `Override: RM ...` when a tag has one. |
| AC-S3-6 | NOT BROWSER-VERIFIABLE | No tag Remove control exists at `a30927e61` (the S3 contract says "No UI in S3"). Covered by the red `tests/test_price_tag_request_tags.py::test_delete_last_tag_422`. |
| AC-S3-7 | N/A | r9 is not on main, so the migration's remap step is the documented no-op. |
| AC-S3-8 | PASS (indirect) | Per-tag resolution is what the rail draws: each tag carried its own row and its own price, and a split line answered two rows where it had answered one. |
| AC-S4-1 | NOT BROWSER-VERIFIABLE | The tag's `set_members` text is drawn to a Konva CANVAS, so no accessibility read can assert on it. Covered by `tests/test_price_tag_tag_render_data.py::test_set_members_text_parts_and_open_group`. |
| AC-S4-2 | PASS (on real data) | Measured against the lane database (SRTBF11834 3550.00, SRTMR11406-WH 75.00, SRTBS01 257.00, SRTBS01-NL 257.00): an UNRESOLVED open group contributes nothing - the open tag showed `LP RM 3,625` = 3550 + 75. Once resolved, every tag showed `LP RM 3,882` = 3550 + 75 + 257, on both split siblings and on the picked one. |
| AC-S4-3 | PARTIAL | The portal read view of PT-202609-0012 DOES show the parts under the line (`SRTMR11406-WH - SRTMR11406-WH`, `Basin: SRTBS01 / SRTBS01-NL`). It shows no price FIGURE - its "Price" section carries the price MODE ("List price") only, which is r7's existing design. The proof/preview half was not reachable: none of these requests has a rendered proof. |
| AC-S4-4 | NOT VERIFIED | Needs a designed tag, a design-ready transition and a worker render; no PDF exists for a combo request yet. |
| AC-X-1 | PASS | Every new control seen was a `SearchableSelect`: the choice-group control, the Package select, the open-row candidate select, "Pick one", and both product pickers (server-searched, paged, not capped). The optional ones carried "Clear selection". |
| AC-X-2 | PASS | No UUID was rendered anywhere on the walk. Combos read by name, parts and candidates by product code, tags by ordinal (1a/1b). |
| AC-X-3 | PASS | The only explanatory sentence found was the one AC-S2-3 licenses: "Marketing will prepare one tag per option". |
| AC-X-4 | PASS | No new motion observed; rows appear and disappear with the existing list behaviour. |

## Defects

### D1 - a tag's price is stale after Split and after Pick one (CONFIRMED, reproducible)

The designer re-reads the REQUEST after either action but never re-resolves the
per-tag display data, so the rail keeps the figures it had before the action and
a freshly split sibling has no figure at all.

Steps (PT-202609-0012, `a78aec2d-3478-4f27-ba25-27a20a976ee2`):

1. Portal: new price tag request, customer I BATH STUDIO, line = SRTBF11834,
   package "3 in 1", leave the Basin group OPEN. Submit.
2. CRM: open the request, Claim, Lines tab, "Design tag 1a".
3. The rail reads `1a | Open: Basin | Qty 1 / LP RM 3,625` (correct: the open
   group contributes nothing).
4. Click "Split into 2 tags". `POST .../tags/{id}/split` returns 200 and the
   rail becomes:
   - `1a | SRTBS01 | Qty 1 / LP RM 3,625`  <- stale, should be 3,882
   - `1b | SRTBS01-NL | Qty 1`             <- NO price at all
5. Reload the same page. Both now read `LP RM 3,882`, which is correct
   (3550 + 75 + 257).

Same on "Pick one" (PT-202609-0011): after `PATCH .../tags/{id}` 200 the rail
still read `LP RM 3,625`; after a reload it read `LP RM 3,882`.

Network confirms it: the last `POST .../resolve-prices` fired BEFORE the
`PATCH`/`split` call and none fired after.

Why it matters: the canvas is what marketing approves, and D3/ADR-0008's whole
point is that the screen and the PDF state the same number from the same call.
Here they disagree until somebody happens to reload - and a newly split tag
shows no price whatsoever, which reads as an unpriced product rather than as a
stale view.

Not fixed here (tester does not touch implementation).

### D2 - the line row's List Price is inconsistent between requests (minor)

On PT-202609-0009 the LINE row of the Lines tab showed `RM 3882.00`; on
PT-202609-0011 the same column was empty while its tag row showed
`RM 3625.00`. The UAC does not require a line-level price (price is a TAG fact
since D4), so this is cosmetic - but a column that is populated on one request
and blank on another reads as missing data.

## AC-S4-4 - the PDF of a split line

Verified, without a worker and without touching the shared `catalogue_render`
queue. The worker's own task function was run INLINE from a one-off shell in the
lane backend, against the lane database and the lane frontend
(`DEALER_KIT_PRINT_BASE_URL=http://localhost:3083`):

```
PT-202609-0009 designing -> proof_ready -> ready
request_tag_sheet_export(...)   -> download 2beb2b2c-09a0-47f5-b498-c9c3b1399fde
generate_tag_sheet_pdf(...)     -> {'status': 'ready', 'bytes': 45749}
```

The print page Chromium rendered carries **two tiles, one per tag**, each with
the package price `RM 3,882` (the cabinet at 3550 plus the mirror at 75 plus the
basin at 257 - the cabinet's list price was changed on the shared dev database
by another lane partway through, which is why this figure is not the 1,882 the
earlier walks recorded). `split-line-pdf-two-tiles.png` is that page.

**One half of AC-S4-4 is NOT shown, and it is not a code fault.** The
requirement is "the candidate's code in the parts text". The resolver produces
that text correctly - the live payload for these two tags reads
`+ SRTMR11406-WH ...\n+ SRTBS01 ...` and `... + SRTBS01-NL ...` - but the tag
this request was auto-cloned onto is the STARTER product block, whose only slot
binding is `barcode`; it carries no `set_members` layer, so there is nothing on
the tile to draw the text into. D4 assumes "every existing template already
carries it", which holds for the published templates and NOT for the starter
block the designer falls back to when no published template matches the family.
A published template with a `set_members` slot would print it. Raised for the
captain rather than fixed here: adding the slot to the starter block changes
every ala-carte tag in the system and is not this slice's call.

## Console

Two entries only, both pre-existing and NOT from this lane:

- `[error] Each child in a list should have a unique "key" prop. ... Check the
  render method of 'Demo1Layout'.` - the known shell warning named in the brief.
- `[warning] Missing 'Description' or 'aria-describedby={undefined}' for
  {DialogContent}.` - raised by a shell dialog, not a lane one; the lane's
  `AddComboModal` does carry a `DialogDescription` (checked in source).

No uncaught page errors (`errors` was empty on every page of the walk).
