# UAC - Series catalogue and pricing, as pages

**Status:** written 2026-08-10, awaiting sign-off. Not implemented.
**Slug:** series-catalogue-and-pricing-pages
**Parent:** `PLAN-standard-products-images-and-recompute.md` (S18 named the products; this prices them)

## Journey

**Who.** The Project Sales admin who owns what Sorento is willing to sell into a project and at
what price. They arrive from the sidebar, not from a quotation.

**What they hold at the start.** A supplier-style sheet per scope -
`products template( sanitaryware).xlsx` - three tabs, 151 product codes, a DEVELOPERS column
holding a price and a DISTRIBUTORS column holding a percentage. They have been maintaining it
in Excel and want it to BE the system's answer, not a thing they retype.

**Step 1 - Series.** Sidebar -> **Series**. A list of series, one row each, the standard list
layout. No paragraph explaining what a series is.

**Step 2 - Open one.** Click the row. A page opens (not a dialog) showing the series' own
fields and, below them, **the products it covers as a table**: code, description, selling
price, max discount. This is the screen they came for - the sheet, in the system.

**Step 3 - Fill it.** Either edit the table in place, line by line, or load the sheet in one
go. Every code the catalogue could not match comes back named, because that is their data
telling them something.

**Step 4 - It is used without them doing anything else.** A quotation quoted from that series
pre-fills the line at the series selling price, and refuses to go below selling price less max
discount. The salesperson never opens this page.

**Step 5 - Price floors, separately.** Sidebar -> **Price Floors**. Its own list, its own form
page. It is a different policy about different products and it stops sharing a screen with
series.

**The one decision the admin makes** is "what does this scope sell, and for how much". Every
other consequence - what a line pre-fills at, what counts as standard, what is a breach - is
derived from it.

## What the sheet actually says (measured 2026-08-10)

| | wares | fittings | shower | total |
|---|---|---|---|---|
| Product codes | 40 | 97 | 14 | **151** |
| Carry a price | 39 | 56 | 0 | **95** |
| Carry a discount | 40 | 16 | 0 | **56** |

- **DEVELOPERS / DEVELOPER** is a **price** (220, 200, 170, 8, 5 ...). All numeric, no junk.
- **DISTRIBUTORS / DISTRIBUTOR** is a **percentage**, written two ways: `6 % MAX` and `8 % MAX`
  in `wares`, `0.06` and `0.1` in `fittings`. Four distinct values across the book: 6%, 8%, 10%.
- **The discount varies per product**, so it belongs on the series-product row, NOT on the
  series.
- **Both are optional.** `shower` has neither column; 56 codes have a price and no discount.
- CENTRAL / NORTHEN / SOUTHERN are present and **entirely empty**. Not modelled. If they ever
  carry values they are a per-region price and a bigger change than this.

## Acceptance criteria

### A. The pages exist and follow the standard layout

- **AC-A1** `Series` and `Price Floors` are two separate sidebar entries and two separate
  routes. The combined "Pricing policy" screen no longer exists.
- **AC-A2** Both lists use the standard scaffold: `Container` + `Toolbar`/`ToolbarHeading`/
  `ToolbarTitle` + breadcrumb, then a `Card` whose `CardHeader className="block"` contains
  exactly one `DataGridListToolbar`. Search, Filters, Columns, Export and Refresh sit inline in
  that toolbar's LEFT cluster; the primary `Add` sits right. **No hand-rolled button row below
  the heading.**
- **AC-A3** No explanatory prose on any of these screens. No subtitle under the page title, no
  `DialogDescription` paragraphs, no helper sentences under fields. Where a term genuinely
  cannot be understood from its label, it gets an info icon with a tooltip, not a paragraph.
- **AC-A4** Clicking a row opens a **detail page**, not a dialog. `Add` also opens a page
  (`/new`). No create-or-edit modal remains for series or price floors.
- **AC-A5** Both detail pages carry the standard header: title, breadcrumb, `RecordNavigation`
  prev/next, and a Back button, exactly as `user-management/users/[id]/layout.tsx` does.
- **AC-A6** Delete stays a hard delete behind `ConfirmDeleteDialog`. A confirmation dialog is
  not "explanation" and is not removed.

### B. The series detail page shows the sheet

- **AC-B1** The page shows the series' own fields (name, brand, categories, active) in an
  editable form on the page. Save and Cancel sit at the bottom; Save is disabled until dirty.
- **AC-B2** Below the form, a **products table**: Product code, Description, Selling price,
  Max discount. It is a `DataGrid` and obeys the DataGrid contract (fixed layout, resizable,
  explicit sizes, truncate + title on long text).
- **AC-B3** Rows are editable in place - pick a product, type a price, type a percentage -
  and added without a dialog, in the same Excel-like way quotation lines already work
  (`InlineLineTable`). Removing a row asks for confirmation.
- **AC-B4** Selling price and max discount are both **optional**. A product with neither is a
  valid row; the cells read as empty, not as zero.
- **AC-B5** Max discount is stored and displayed as a **percentage** (`6` = 6%), whichever
  form the sheet used. `6 % MAX` and `0.06` both import as `6`.
- **AC-B6** Loading a sheet still reports every unmatched code verbatim and copyable. The
  reporting from S18 does not regress.
- **AC-B7** A product may appear once per series. Loading a sheet that names it twice is not an
  error; the last row wins and the duplicate is reported.

### C. What the numbers do

- **AC-C1** **Pre-fill.** On a quotation whose scope is quoted from series S, choosing a
  product that S names sets the line's unit price to S's selling price for that product,
  instead of the product's list price. The salesperson can overtype it.
- **AC-C2** If S does not name the product, or names it with no selling price, the line
  pre-fills from list price exactly as today.
- **AC-C3** **Floor.** For a line on a scope quoted from S, where S names the product AND
  gives it both a selling price and a max discount, the floor is
  `round(selling_price * (1 - max_discount_pct/100), 2)` - 220 at 6% is **206.80**. Any
  `PriceFloorRule` covering that product is ignored for that line.
- **AC-C4** Where S says nothing - product not named, or no selling price, or **no max
  discount** - `PriceFloorRule` applies exactly as today. A missing discount is NOT read as
  "zero discount allowed": 56 of 151 codes have a price and no discount, and inventing a hard
  floor from a blank cell would flag them all.
- **AC-C5** The below-floor message names which rule bound the line ("series" or the floor
  rule's level), because a refusal nobody can act on is worse than no refusal.
- **AC-C6** Recompute (S19) re-applies all of the above to an open version and reports what
  changed, including a price that moved because the series price moved.
- **AC-C7** Floors and pre-fill are evaluated for the WHOLE version in a bounded number of
  queries, never one per line - the rule the picture column already follows.

### D. Not in scope, stated so nobody assumes it

- Regional pricing (CENTRAL / NORTHEN / SOUTHERN). Empty in the sheet; would be a per-region
  price dimension.
- Repointing the 233 quotation lines that name another company's product. Separate data fix.
- Changing what "standard / non-standard" means. S18 decided that and it is unaffected.

## Definition of done

1. Two standalone pages each for Series and Price Floors (list + detail), no modals, no prose.
2. The toolbar arrangement matches the users list exactly.
3. The 151-row sheet loads with its prices and discounts, unmatched codes reported.
4. A series-quoted line pre-fills at the series price and refuses below the derived floor,
   with a message that names the binding rule.
5. pytest for the floor resolution and the importer's two percentage spellings; vitest for the
   products table states; one Playwright pass through sidebar -> Series -> row -> edit -> save.
6. Verified at 375px and 1280px on a prod build, against real data.
