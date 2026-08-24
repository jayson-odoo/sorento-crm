# UAC - SCM plan screen: captain feedback round 2 (2026-08-15)

**Status:** Captain decisions taken 2026-08-15 (hands-on session, 12 screenshots, brief at
`firstmate/data/scm-feedback-round-2026-08-15.md`). Every item below is a captain decision
unless marked "investigated"; the investigated ones are answered in this file with what the
data says. Ships as four PRs (see PLAN). Captain merges.

## Journey

**Who.** The buyer on SCM -> Reorder Planning, deciding one plan row at a time. A row is a
product AT a location (SRTWCY8840 @ BRW-BB). Every popover on the row exists to answer one
question the buyer has before pressing Accept, so every popover must answer it for THIS row.

**Step 1 - "how much is really committed here?"** The buyer opens Demand behind this row on
the BRW-BB row and sees BRW-BB's own open sales orders, totalling the same number the row
shows in its SO column, each with the customer who ordered it and the price they pay. Nothing
from BRW-IB or BRW-NTC is in that list unless the plan itself netted those together (pool
netting on), and then the header says so.

**Step 2 - "is this product worth buying at all?"** The buyer opens the health popover and
reads one line: `Suggestion: Keep selling` or `Suggestion: Discontinue`, then the metric rows,
then the two buttons. No prose above, no disclaimer below. The trend popover shows a chart
big enough to read, legend in one row, and Who bought it names real customers; where the order
carries no customer the row says so honestly. Any customer row expands to the sales orders
behind it (SO, date, qty, unit price), which is where the "sells RM 0.94" question gets
answered.

**Step 3 - "what does the decision actually do?"** Hovering the Accept button shows a table
(location | qty to use, then the buy line), not a run-on sentence. In the ledger the Use stock
row is a toggle; on, each source location has an editable quantity, and the buy quantity
follows. The sources offered are only the ones the setting allows: by default the row's own
site (its pool), never another site. Money reads one way everywhere: `RM 105.00`.

**Step 4 - "what does it look like?"** The buyer clicks the photo icon on the product cell
and sees the product's primary photo, the one chosen in Dealer Kit -> Brochure images. No
photo yet: the popover says so and links to that page.

**What they hold at the end.** A decision they made with the row's own numbers, a cover split
they set themselves, and confidence in what the product is.

## AC-1 Demand popover is scoped like the row (brief A)

- **AC-1.1** With pool netting OFF (the default) the popover for row (product, warehouse W)
  lists only open sales-order lines whose `warehouse_id = W`, plus the product's unlocated
  lines (`warehouse_id IS NULL`) ONLY when this row is the one the engine landed them on
  (`inputs.unlocated_demand > 0`), and those lines are marked unlocated. The header total
  equals the row's `outstanding_sales` (`inputs.committed`).
- **AC-1.2** With pool netting ON the popover lists the pool's members and the header names
  the pool ("sits at BRW-BB, BRW-IB (pool BRW)"), so the number still equals the row's own.
- **AC-1.3** Netting is unchanged: `committed_v` already nets per (product, warehouse) and
  pools only when `pool_netting` is on. Pinned by a test asserting popover total == row
  committed on a two-warehouse fixture, both modes.
- **AC-1.4** Each line shows customer name (or the honest fallback of AC-4.3) and unit price
  when the line carries one.

## AC-2 One money format (brief B)

- **AC-2.1** "Last purchase" reads `RM 105.00` (base currency) or `USD 12.50` (foreign), never
  `RM 105 MYR`. Uses the shared `fmtSupplierCost`.
- **AC-2.2** No hand-rolled money strings remain on the plan screen: `PoWorklistView`
  (`${currency} ${n.toLocaleString}`) and `PlanMethodologySheet` (own `Intl.NumberFormat` +
  literal `RM`) route through `scm/lib/format.ts`. A vitest greps the plan tree for
  `toLocaleString('en-MY')` / `new Intl.NumberFormat` outside `format.ts` and fails on a hit.

## AC-3 Decision breakdown as a table; cover sources constrained; per-location editable (brief C)

- **AC-3.1** The Accept button's hover is a table: rows `location | use qty`, then a `Buy`
  row, then a total. The button label stays short (`Stock 1,442 + Buy 1,778`). The decided
  row summary uses the same table on hover.
- **AC-3.2** New policy knob `cover_scope` on `scm.reorder_policy`: `own_pool` (default) or
  `all_locations`. Global scope row only, edited in SCM -> Policies -> Planning mode panel
  as a two-option select with the label "Cover from" and options "Own site only" / "Any
  location". Migration adds the column with default `own_pool`; `bootstrap_env` replays.
- **AC-3.3** With `own_pool`, cover sources for a row are limited to warehouses in the row's
  pool (`COALESCE(pool_warehouse_id, id)` equal), still excluding the row's own warehouse and
  still requiring `counts_as_available`. With `all_locations` behaviour is today's. The
  cover-sources map is keyed by product (two rows of one product can sit in different
  pools), so it carries each source's `pool_warehouse_id` plus the policy value and the
  per-row filter runs where the row is known: in the FE (`coverPlan.sourcesInScope`),
  mirrored by the backend `propose_cover` (test-only mirror of record). The FE never RENDERS
  an out-of-scope source. Pinned by test on both sides: three warehouses, two in one pool,
  `own_pool` offers one source, `all_locations` offers two. Data note: 80 of 82 warehouses
  carry a pool (all `BRW-*` pool to `BRW`), so `own_pool` means "my site" in practice; a
  self-pooled warehouse (PJ-SR) is correctly offered nothing.
- **AC-3.4** Ledger COVER BEFORE BUYING: `Use stock` is a toggle. On, one row per offered
  source: `code | free qty | editable use qty` (0..free), sum = cover qty, buy = gap - cover
  clamped at 0, then MoQ/multiple rounding as today. Off, cover = 0. The recorded decision's
  `stock.sources` carries the edited quantities. Same math helper as the decision cell's
  Adjust mixture, so the two never disagree.
- **AC-3.5** Default quantities in that table are the engine's proposal (same-segment first),
  so a buyer who never touches it gets today's answer.

## AC-4 Drill into the sales orders behind price and customer (brief D)

- **AC-4.1** In the trend popover, each Who bought it row expands in place to the sales-order
  lines behind it in the trend window: `SO | date | qty | unit price`, newest first, capped at
  20 with a "N more" tail. Endpoint returns the lines for (run, product, segment, customer key).
- **AC-4.2** The demand popover lines carry customer name and unit price (AC-1.4), so the
  "sells RM 0.94" question is answerable from either popover.
- **AC-4.3 (investigated)** "Unnamed customer" = `sales_orders.customer_id IS NULL`, 2,546 of
  2,548 outstanding-book uploads (`source_system = scm_upload`) and 2,021 of 11,006 sales-
  history uploads. Cause on the outstanding book: the importer reads the debtor code but
  deliberately never linked the customer ("the day a consumer exists"). That day is now:
 - the outstanding-SO import links `customer_id` by debtor code exactly as the PO side
    links suppliers, and keeps `debtor_code` on the order (new nullable column
    `sales_orders.debtor_code`, written by both SO importers) so an unresolvable code is
    still attributable;
 - the trend and demand labels fall back in order: customer name -> `Debtor <code>` ->
    `No customer on order`. "Unnamed customer" is retired;
 - existing rows: a re-upload of the outstanding book relinks them (S3 async makes that
    cheap). No backfill script - the debtor code was never stored, so there is nothing to
    join on. Stated in the PR.
- **AC-4.4 (investigated)** "No order history" beside an open SO: the trend reads
  `sales_orders.order_date` in the last 24 months and the outstanding-book importer never
  wrote `order_date` (SO410884 has none), so a row can carry open demand and no dated
  history. Fix both ends: the SO import fills `order_date` from the file's `SO DATE`
  (header fill, existing value wins), and the trend popover's empty state reads
  `No orders dated in the last 24 months` plus, when the row has open demand, `Open now: 51
  (see Demand)`.

## AC-5 Health popover wording (brief E)

- **AC-5.1** Top line is exactly `Suggestion: Discontinue` or `Suggestion: Keep selling`
  (`Suggestion: -` while facts are loading / when there is no verdict).
- **AC-5.2** Removed: "The product is earning its place.", "The factors argue for
  discontinuing this product.", the bottom "Based on our own orders and stock only. A
  discontinue decision is recorded here; marking it in AutoCount stays your job.", and the
  trend popover's "Based on our own orders only.". Metric rows and the two buttons stay; the
  `suggested` hint beside the suggested button stays.

## AC-6 Trend chart readable (brief F)

- **AC-6.1** Legend is one horizontal row at the top; chart height at least 240px inside a
  popover at least 30rem wide (capped at 92vw); y-axis has at most 5 ticks, integer labels via
  `fmtInt`, min 0; x labels do not overlap at 12 months.

## AC-7 Product primary photo on the plan row (brief G)

- **AC-7.1** The product cell carries a photo icon. Click opens a popover with the product's
  primary photo (`product_attachments.is_primary`, the same flag Dealer Kit -> Brochure
  images sets), falling back to the product's first catalogue image when none is flagged
  (the same reader and order the catalogue tile uses; on the live run 744 of 762 imaged
  products have no flag, so a literal `is_primary` rule would blank them). Icon is dimmed
  when the product has no image at all; the popover then reads `No primary photo yet` with
  a link to Dealer Kit -> Brochure images. When a fallback image is shown the popover keeps
  a one-line footer link to that page, so the "choose the primary" loop still exists.
- **AC-7.2** One cheap request per run for the icon state (`GET
  /reorder-runs/{run}/product-images` -> `{has_image: {product_id: true}}`, no signing),
  fetched lazily on first icon open; the signed URL is fetched per product on popover open
  (`GET /reorder-runs/{run}/product-images/{product_id}` -> `{url, is_primary}`), never
  hundreds of signatures in one request.
- **AC-7.3** Dealer Kit -> Brochure images is where "mark as primary" lives today (that page's
  chosen image IS `is_primary`); its page title/help copy says so in one line so the buyer
  knows where to go. No new dealer-kit surface.

## Out of scope (recorded)

- Per-location `cover_scope` (policy scopes other than global): the global knob is the
  smallest sensible one; scoped rows can follow if the captain asks.
- Storing the salesperson on the trend ("Who sold it") - separate item, unchanged.
- Backfilling `debtor_code` for rows imported before this change (nothing to join on).
