# PLAN - Series catalogue and pricing, as pages

**Status:** written 2026-08-10, approved and **T1-T7 implemented the same day**.

## T7 - the 2026-08-10 review round

Ten items off a screen-by-screen review. Seven were changes; three were questions whose
answer turned out to matter more than any of the changes.

**The finding.** No quotation has a series bound - `series_id` is NULL on all eight. With no
series, `is_in_series` returns true for everything, so **nothing is checked**, and the 49
lines still flagged `is_non_standard` on QT-004188 v5 are stale leftovers from an earlier
state. Every line that gets edited recomputes to false, which is exactly what made BT009
look "fixed" by saving it. The feature is dormant, not working. Left alone on the client's
instruction: flags now update live when a line's product changes, and `Recheck alerts`
(already built, S19) pulls a config-level change. No data was rewritten.

**The two badges were being conflated.** `Off-catalog` means the line has NO product linked;
`Non-standard` means the product is outside the series. Adding a code to a series can never
clear the first. Off-catalog is now read off the LIVE draft, so picking a product clears it
without a save. Non-standard and below-floor stay the server's verdicts, but are WITHHELD
once the draft diverges from the row they judged: a verdict about the previous product shown
against the new one is a confident wrong answer, which is worse than none.

**SPRTWT5913 is correctly non-standard.** The sheet carries `SRTWT5800`-`SRTWT5815`; `SPRT`
is a different code family and was never among the 92. Separately: that code exists TWICE in
`products` under two different categories, which is its own problem and is not addressed
here.

**The sheet load is now queued.** The 9.2 MB workbook was parsed inside an `async def`
route, so it ran on the event loop and stalled every request in the process. It now enqueues
onto `project_docs` (this checkout's own queue - a worker from another worktree listening on
`imports` would claim the job without having the task module) and returns 202 with a job id
the browser polls. Verified end to end in the browser on the client's real workbook: progress
panel, then 92 added / 153 read / 141 unique / 49 named - identical to the synchronous
figures.

Also: search over the products table (Ctrl-F only finds what is scrolled into the DOM, so it
answered 0/0 for products that were plainly there), `RM` and `%` printed in the cells rather
than only in a header that scrolls away, Delete moved into a gear menu away from Back, and
prev/next via the shared `RecordNavigation`.

## T8 - on-the-spot verdicts (2026-08-12)

The client rejected T7's withholding: "the computation of whether it is non standard or off
catalog needs to be on the spot, cannot wait until I save". T7 withheld the server verdicts
once a draft diverged, which was honest but silent - BM107 should read Non-standard the
moment it is picked.

The verdicts still cannot be computed in the browser (series membership counts nominated
CATEGORIES the browser never fetched; the floor walks the category ancestry), so the answer
is `GET /quotations/{id}/line-verdict?product_id=&unit_price=` - a read-only judgement by
the SAME `is_in_series` / `resolve_floor` the save runs. The editor asks per settled draft
(debounced 400ms, `useLineVerdict`), holds the previous verdict while the next loads, and
never writes. One implementation, asked at two moments.

**Defect the tests caught before the browser did:** on divergence the query fired against
the still-settling PREVIOUS draft values, judging the old product against the new one - the
exact confident-wrong-answer the design exists to prevent. Fixed with a caught-up guard:
the query is enabled only once the debounced values equal the on-screen ones.

Also in T8: search over the quotation lines (a `rowFilter` prop on `InlineLineTable` that
HIDES rows at render - filtering the `rows` prop would tear unsaved drafts out of the
table's state; item numbers hold and totals still sum the whole version), and prev/next
between the project's quotation documents in the document header (list mode off the cached
documents query, hidden mid-edit-session).

Browser-verified on QT-004188 v5 with a throwaway edit session, cancelled unsaved: picking
BM107 raised the Non-standard count 56 -> 57 with no save; the search box filters and shows
its own empty state; both prev/next buttons render (3 documents). Version count confirmed
still 5 afterwards - nothing was written.

Cover: +4 pytest (BM107/C-FH14 on the spot with nothing written, off-catalog only under a
series, half-typed price judged as no price, series floor applied live with the value
carried), editor vitest rewritten from "withholds" to "asks" (+ below-floor-as-typed, +2
line-search), 873 project-sales vitest green.

**Still open: `project_series.brand_id` does nothing.** The column exists, the form has a
picker, and no service reads it. It should either scope the product picker or come off the
form; it was not changed without a decision.

Cover for T7: 104 backend tests across six suites, 867 frontend. New: four backend (the
upload queues rather than reads, the task applies the sheet and reports the misses, a
deleted series fails the job instead of raising, an unknown mode is refused before anything
is queued) and eleven frontend (queued progress / finished report / failed job, the currency
and percent prefixes, search by code and by name, the search-found-nothing empty state, and
the two live-badge claims).

**A gotcha worth writing down:** running pytest while a `--reload` uvicorn is up against the
same database produced 40-81 bogus failures (`relation "companies" does not exist`) that
vanished the moment the API was stopped. Same family as the known exclusive-DB rule; the
reloader is the part that makes it bite.

Cover: 101 backend tests across the six touched suites, 882 frontend tests (12 new across
`SeriesSheetLoader` and `SeriesProductsTable`), and a persisted Playwright spec,
`e2e/series-catalogue-pricing.spec.ts`, 4 tests green in 13s. The spec creates a `zzt-e2e`
series and deletes it through the UI, so it exercises the destructive path and leaves the
client's own series untouched.

**One acceptance criterion is NOT browser-verified: AC-C1, the line pre-fill.** It is wired
and its floor half is covered by pytest, but observing it needs a scope BOUND to a series
that PRICES the product, and no quotation is bound to the Sanitaryware series today
(`quotation_count` is zero). Binding one changes what counts as standard on a real
quotation, so it was not done unprompted.

Verified on the client's real workbook, loaded through the new page into a throwaway series:
92 products added, 153 codes read, 141 unique, 49 unmatched and reported - figures identical
to S18's own measurement. 51 products took a price, and **30** of those a floor: `C-FH14`
5.00 at 6% -> 4.70, `CB1508ASS` 20.00 at 6% -> 18.80. The other **21 priced products got no
floor at all**, which is AC-C4 doing its job on live data - under the rejected reading each
of them would have been in breach on the first cent of discount.
**Slug:** series-catalogue-and-pricing-pages
**UAC:** `series-catalogue-and-pricing-pages-acceptance-criteria.md` (governing)
**Parent:** `PLAN-standard-products-images-and-recompute.md` - S18 named the products, this
prices them.

## Why

Two things, from the 2026-08-10 review of the Pricing policy screen.

**The screen breaks our own rules.** It explains itself in prose ("What each scope is supposed
to be quoted from, and how low its price may go"), it puts its controls in a row under the
section heading instead of inline in the standard toolbar, and it edits everything in dialogs.
The user's standing principle: *if the system needs explaining, the design failed*. The users
list and user detail are the reference.

**It is missing the thing it is for.** A series today records only WHICH products it covers.
The client's sheet also records, per product, what that product SELLS for and how much further
discount a distributor may take. Without those two numbers the sheet is not in the system, and
the admin keeps quoting from Excel.

## The finding that shapes the model

`products template( sanitaryware).xlsx`, measured 2026-08-10:

```
wares      codes= 40  with_price= 39  with_discount= 40
fittings   codes= 97  with_price= 56  with_discount= 16
shower     codes= 14  with_price=  0  with_discount=  0
TOTAL      codes=151  priced= 95      discounted= 56
distinct discounts: '6 % MAX' x6, '8 % MAX' x12, '0.1' x22, '0.06' x16
```

Three consequences, and each kills an obvious alternative design:

1. **The discount is per PRODUCT, not per series** - 6%, 8% and 10% all appear in one book. A
   single "distributor margin" field on the series cannot express it.
2. **Both numbers are optional** - `shower` has neither column, and 56 codes carry a price with
   no discount. Nullable columns, and a blank must read as "not stated", never as zero.
3. **The percentage has two spellings** - `6 % MAX` (text) and `0.06` (fraction) mean the same
   6%. The importer normalises both to `6`; the column stores percent.

CENTRAL / NORTHEN / SOUTHERN exist and are entirely empty. Not modelled. Importing an empty
column as a real dimension is how you end up with a pricing model nobody can explain.

## Decisions taken (answered by the user 2026-08-10)

- **Series floor WINS; the floor rule is the fallback.** For a line on a scope quoted from
  series S where S gives the product a price and a discount, the floor is
  `selling_price * (1 - pct/100)`. `PriceFloorRule` is ignored for that line. Where S is
  silent, `PriceFloorRule` applies exactly as today. One rule binds a line, never two - the
  same reason `product_attachments.is_primary` is the only picture decision.
- **A missing max discount is silence, not zero.** It falls back to `PriceFloorRule`. Reading a
  blank cell as "no discount permitted" would put 56 products on a hard floor nobody set.
- **The series price pre-fills the line, overridable.** That is the point of recording it. The
  below-floor flag then evaluates whatever the salesperson actually typed.
- **Pages, not dialogs.** The users screens are the reference for layout and component
  vocabulary; note they edit in a modal and this deliberately does NOT copy that part.

## Slices

| # | Slice | Ships |
|---|---|---|
| **T1** | Model + migration | `selling_price NUMERIC(12,2) NULL` and `max_discount_pct NUMERIC(5,2) NULL` on `project_series_products`. Defensively re-runnable, like 331/332. No backfill: the numbers do not exist yet. |
| **T2** | Import + API | The paste and upload routes read the price and discount columns, normalising `6 % MAX` / `0.06` / `6` to `6`. Per-row read/write endpoints for the products table. `product_count` gains `priced_count`. Unmatched-code reporting unchanged. |
| **T3** | Series pages | `/project-sales/series` (list) and `/project-sales/series/[seriesId]` (detail: form + products table). Standard scaffold, `DataGridListToolbar`, no prose, no dialogs. Products table is an `InlineLineTable` so a row is added and typed like a quotation line. |
| **T4** | Price Floors pages | `/project-sales/price-floors` (list) and `/.../[ruleId]` (detail form). Same scaffold. The old combined `/project-sales/pricing` route redirects to `/project-sales/series` so existing links and the sidebar entry do not 404. |
| **T5** | Pricing engine | `resolve_floor` consults the series first (AC-C3/C4) and returns WHICH rule bound the line. Pre-fill on product select (AC-C1/C2). Recompute picks up both. Bounded queries per version. |
| **T6** | Tests + browser | pytest for floor resolution, the two percentage spellings, and the optional-field matrix; vitest for the products table states; Playwright sidebar -> Series -> row -> edit -> save; 375px and 1280px on a prod build. |

T1 and T2 are backend-only and unblock T3. T5 is the only slice that can change what an
existing quotation says, so it lands last and behind its own tests.

## Contract (Phase 1 output, written before the FE is built)

`GET /api/v1/project-sales/config/series/{id}/products`

```jsonc
{ "data": [ {
    "product_id":  "uuid",
    "product_code": "CWC7601-S-RL",
    "product_name": "ONE PIECE WASHDOWN WATER CLOSET",
    "selling_price": "220.00",      // null = not stated
    "max_discount_pct": "6.00",     // null = not stated, NOT zero
    "derived_floor": "206.80"       // null unless BOTH are set. Server computes it once.
} ] }
```

`PUT .../config/series/{id}/products` replaces the set (the shape the sheet upload already
uses); `PATCH .../config/series/{id}/products/{product_id}` edits one row from the table.

`derived_floor` is computed server-side and never in the browser: it is the number a refusal
is argued from, and two implementations of one formula is the defect this codebase keeps
finding.

## Risks

- **T5 changes live quotations.** 233 lines across the database already name another company's
  product; those resolve to nothing and must keep falling through to today's behaviour rather
  than acquiring a series floor. Covered by AC-C4 and a test.
- **`PriceFloorRule` becomes partially dead** for series-covered products. It is not removed:
  it still governs everything the series does not name, which is most of the catalogue.
- **The products table can grow.** 151 rows here, and the DataGrid contract plus a bounded
  query budget (AC-C7) is what stops it becoming the 52-round-trip mistake the picture column
  already avoided.

## Open question for sign-off

**Where do these two entries live in the sidebar?** Proposal: replace the single
`Pricing Policy` entry with `Series` and `Price Floors`, both under Project Sales, adjacent to
`Setup`. The alternative - keeping a `Pricing Policy` parent with two children - adds a click
to reach either. Easy to change; not worth blocking on.
