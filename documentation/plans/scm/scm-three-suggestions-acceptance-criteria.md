# S13 - The engine in purchasing's chair: three suggestions per row

Status: user said go 2026-08-10. S13b BUILT (demand_origin column, committed_v split, set-aside report + banner, Side column, structured quantity cell, supersede wording). S13c BUILT (level+qty upload channel, alias mapper, hand-set-level conflict rule). S13d BUILT (trajectory verdicts, line graph popup, both baselines, customers). S13e BUILT (thresholds on scm.reorder_policy + policy modal, cheaperAlternative in base currency, "Ask <code> instead" headline on recent prices, popover footnote otherwise; live run has 0 qualifying rows because the engine already sits on the cheapest ranked supplier). S13f BUILT (run hook writes trajectory-adjusted suggested_level per plan pair, level itself never touched; "AutoCount level" column with arithmetic popup; run-level change list + CSV; suggested-0-on-nothing reads "No level needed"). S13 COMPLETE.

## Why

Course correction, user, 2026-08-10 (verbatim anchors):

> "I want our engine to mimic the behavior of how the user does it, but with added value ...
> the order inquiry is the demand because the SO is processed by the customer service team ...
> they will come up with order inquiry, which are the things that they think the company
> should buy and pass to purchasing ... purchasing will compound this, and this is what our
> engine should do."

> "order inquiry is only for project side. So for dealer side is exactly based on the sales
> order."

> "So the first suggestion is the quantity whether to buy or use stock and how much for each
> of the action. Second suggestion is whether we want to buy with the same cost as last time
> or change supplier or request for quotation. The third suggestion is I should suggest the
> reorder level [for] AutoCount."

> "think of it like I'm a reviewer. I'm reviewing your work, reviewing your calculation. So
> for me to review, I need data to validate."

> "it needs to be presented to the least tech savvy person in the world."

Locked answers (same conversation): purchasing CAN supersede CS, so use-stock stays suggested
on project lines and is worded as a supersede; AutoCount reorder-level file columns are
assumed until a sample arrives, behind the alias mapper; **everything configurable from day
1, never "later"**.

## Journey

The actor is the buyer (purchasing). They arrive at Reorder Planning from the sidebar.

1. **They upload what the plan eats**: outstanding SO, outstanding PO, Order Inquiry, supplier
   details (MoQ, last cost, lead time), and - new - the AutoCount reorder level + reorder
   quantity listing. Stock is already flowing. Each upload has the same Test/Confirm dialog.
2. **They run the plan.** The engine sits where purchasing sits: project demand comes from the
   Order Inquiry (CS already filtered it), retail demand comes straight from the outstanding
   sales orders. A row appears when a product falls below its reorder level.
3. **Each row makes three suggestions, in plain words**:
 - **How many** - buy N / use stock M from a named place / both. Behind it: demand, on hand,
     incoming (SPO allocations), on order (outstanding PO), and whether this product's demand
     is holding up or dying off.
 - **What price** - use the last price / ask this other supplier / get a new quote.
 - **What level** - "set AutoCount reorder level to N", so the NEXT planning run triggers at
     the right time.
4. **They review, not calculate.** Every suggestion opens the data that justifies it - last 3
   months of orders (retail) or last 12 (project), who bought it, who sold it, what we paid
   and when. Project and retail are never mixed in one figure.
5. **They decide** buy / use stock / skip per row (exists today), and check the budget at the
   end (exists today). What they hold at the end: a decided plan, ready for the PO worklist,
   plus a list of level changes to carry into AutoCount.

## The slices

### S13b - demand: Order Inquiry for project, sales orders for retail

* **AC-S13b.1 [BE]** GIVEN a planning run, THEN project-class demand is read ONLY from
  orders the Order Inquiry created (`source_system = scm_order_inquiry`, or CS-adopted
  successors of those orders), and retail/dealer-class demand ONLY from the outstanding SO
  book. One order never counts twice - adoption (PLAN-scm-order-inquiry-as-demand) keeps
  identity single.
* **AC-S13b.2 [BE]** (DECIDED by user) GIVEN a project-class outstanding SO that no Order
  Inquiry names, THEN it is NOT demand, and the run reports how many such orders were set
  aside and their total quantity - excluded but counted, never silently dropped.
* **AC-S13b.3 [FE]** GIVEN the plan grid, THEN every row states which side it belongs to
  (Project / Retail), and the summary tiles split by the same line.
* **AC-S13b.4 [FE]** GIVEN a project row with free stock elsewhere, THEN use-stock is still
  suggested, worded as a supersede: "CS asked to buy 50; 20 sit free at BRW - use them?"
* **AC-S13b.5 [T]** A file exercising both orderings: OI first then CS book, CS book first
  then OI. Demand identical in both.

### S13c - the AutoCount reorder level + reorder quantity upload

* **AC-S13c.1 [BE]** A new upload kind on the existing reorder-page channel ingesting, per
  product (and warehouse where the file carries one): reorder level and reorder quantity.
  Columns are ASSUMED (`Item Code`, `Location`, `Reorder Level`, `Reorder Qty`) and mapped
  through `import_field_alias`, so the real AutoCount export maps without code.
* **AC-S13c.2 [BE]** Rows land in `scm.reorder_level` with `source = 'autocount'`. Same skip
  rules as every feed: unknown item named and skipped, never invented. Reconciliation: same
  then skip, diff then update, new then create.
* **AC-S13c.3 [BE]** A hand-entered level is not silently overwritten by an upload; the upload
  wins only over its own prior uploads. Conflicts are reported, not resolved by upload order.
* **AC-S13c.4 [FE]** Test/Confirm dialog like every other feed, green/red/amber.
* **AC-S13c.5 [BE]** The uploaded reorder quantity is stored and offered as the suggestion's
  starting point where present; the engine's own computed quantity is shown beside it when
  they disagree.

### S13d - is this demand going to last? (order more, enough, or less)

* **AC-S13d.1 [BE]** (DECIDED by user: BOTH comparisons, side by side) GIVEN a product+side,
  THEN the run computes its trajectory over the configured window - retail default 3 months,
  project default 12 months - against BOTH baselines: the window immediately before it AND
  the same window last year. The verdict (rising / holding / falling / gone quiet) leads with
  the immediate comparison; the year-ago comparison sits beside it, named absent when the
  history is shorter than a year.
* **AC-S13d.2 [CONFIG]** Both windows live on `scm.reorder_policy` (new columns), editable in
  the existing planning-config UI, from day 1. No hardcoded window anywhere in the path.
* **AC-S13d.3 [FE]** GIVEN a row, THEN the quantity suggestion carries the trajectory in plain
  words: "orders rising - consider more", "no orders for 4 months - buy just enough", never a
  bare percentage as the headline.
* **AC-S13d.4 [FE]** GIVEN the popup, THEN it shows the orders behind the verdict: a LINE
  GRAPH of month-by-month quantity (user: "i need this kind of trend to be in a line graph so
  it is easier to relate"), with the table of months beneath it, WHO bought it (customer
  names), and WHO sold it (salesperson/agent where the source carries one; named absent where
  it does not).
* **AC-S13d.5 [FE]** Project and retail trajectories are never merged into one figure.
* **AC-S13d.6 [BE]** Sellability: where purchase dates and sales dates both exist, the popup
  states how long stock took to sell after arriving - a fact, not a score.

### S13e - the price suggestion becomes three-way

* **AC-S13e.1 [BE][FE]** GIVEN a chosen supplier whose last price is usable AND an alternative
  supplier whose last price for the same product is materially lower (threshold configurable,
  default 5%), THEN the suggestion is "ask <supplier> - we paid them X, Y% less", with the
  same-currency-only comparison rule as S12c.
* **AC-S13e.2 [CONFIG]** The staleness window (today a 180-day constant) and the movement
  threshold (5%) move to `scm.reorder_policy`, editable from day 1. S12c already returns them
  in the payload; they stop being constants.
* **AC-S13e.3 [FE]** The three outcomes read as actions: "Use last price" / "Ask <supplier>
  instead" / "Get a new quote". Popup carries the receipts, as now.

### S13f - suggest the level to set back in AutoCount

* **AC-S13f.1 [BE]** (DECIDED by user: plan rows only, not the whole catalogue) GIVEN a run,
  THEN for each product+warehouse below or near its level the engine writes `suggested_level` + `suggestion_basis` onto `scm.reorder_level` (columns
  already exist): demand-per-window x cover months, using the policy's existing
  `level_study_months` / `level_cover_months`, trajectory-adjusted (rising demand rounds up,
  dying demand rounds down).
* **AC-S13f.2 [FE]** GIVEN a row, THEN the third suggestion reads "Set AutoCount level to N
  (now L)" with the arithmetic in the popup.
* **AC-S13f.3 [FE]** A run-level export/list of every suggested level change, so the user can
  carry them into AutoCount in one sitting - AutoCount stays the owner of the level; we only
  advise.
* **AC-S13f.4 [BE]** A suggestion never overwrites `level` itself. Accepting it in AutoCount
  and re-uploading (S13c) is the loop.

## Presentation doctrine (governs every slice above)

* The user is a REVIEWER. Row = suggestion in plain words; popup = the data validating it.
* **The quantity suggestion is STRUCTURED, not a sentence** (user markup 2026-08-10: "I need
  it to be more structured and organized, instead of like a sentence"). Labeled parts, one per
  line - Use stock: 6 from BRW-BB / Buy: 182 / Trend: orders rising - never a comma-joined
  sentence. This supersedes the S12b sentence style for the quantity cell; the popup keeps
  prose where prose explains.
* **Purchase currency is RMB** - every supplier is in China (user, twice now). The per-product
  purchase currency field (S10f) defaults to CNY; mocks and examples show RMB. The 2020 ledger
  labels most lines USD/MYR - what a historical line SAYS is displayed as recorded, and the
  relabel/rate decision stays open as task 32.
* Least tech-savvy person standard: no trade vocabulary on any row label (pinned by test since
  S13a). Numbers carry their meaning ("5 years 8 months ago", never a bare date).
* Project and retail segregated on every surface: tiles, rows, popups, exports.

## Decisions from the user's markup (2026-08-10)

1. Project SO not named by any OI: **set aside and counted** - the engine respects CS's
   filtering (AC-S13b.2).
2. Trajectory baseline: **both, side by side** - immediate window leads, year-ago beside it
   (AC-S13d.1). Trend rendered as a **line graph** in the popup (AC-S13d.4).
3. Level suggestions: **plan rows only** (AC-S13f.1).
4. Quantity cell: **structured, not a sentence** (presentation doctrine).
5. Currency: **RMB** for purchases, settable per product, defaulting CNY (presentation
   doctrine + task 32 still open for the historical relabel).

### S15 - the four ways to cover a shortage, all suggestive (user, 2026-08-11)

> "buy (when no PO and no SPO, and even no stock), use PO (when there is outstanding PO),
>  use SPO (when there is outstanding SPO), use stock (when there is stock) ... this should
>  remain suggestive ... I was expecting the system to suggest me to use the PO quantity
>  and don't need to order"

Order of preference mirrors the buyer's seat: use what we own (stock), then what is
arriving (SPO), then what is ordered (PO book), and buy only the remainder.

* **AC-S15.1 [FE]** GIVEN a buy row whose warehouse has outstanding PO quantity, THEN the
  suggested action offsets the shortage against it: "Use PO 504" replaces the buy when it
  covers fully, "Use PO 100 + Buy 100" when partial. The engine's netting is unchanged -
  the PO book (an AutoCount import that can be stale) never silently nets a buy away.
* **AC-S15.2 [FE]** GIVEN the buyer agrees, THEN "Use PO" is a recordable decision like
  "Use stock": it orders nothing, costs nothing, and is counted in the totals.
* **AC-S15.3 [BE][FE]** The popup names the receipts: each open PO line (number, remaining
  quantity, expected date) behind the offered figure, served per run.
* **AC-S15.4 [FE]** Incoming SPO is ALREADY inside the net position (incoming = allocation,
  the standing rule), so it is never offered as a second offset - instead the row says
  "N arriving is already counted", and a row fully rescued by SPO lands in Covered with
  the SPO named, not a bare "covered".
* **AC-S15.5 [FE]** The suggested-action filter gains the new kinds.
