# SCM Purchasing and Fulfilment - acceptance criteria

> Status: DRAFT 2026-08-03, written FIRST per methodology, grilled with the user before any
> code. Source material: `Purchasing_SCM.pdf` (swimlane, Project CS / Josephine / Joey / Mr Loo
> / Ms Tee / Supplier), `(04).03.2026 MARYAM TUJU RESIDENCE.xlsx` (order inquiry),
> `2026-7-27 库存明细.xlsx` (supplier inventory), `2026-7-31 SORENTO 预装清单.xlsx` (pre-load
> list). Decisions: ADR-0011 (one engine, dated Coverage Timeline), ADR-0012 (recompute-and-diff).
> Glossary: `CONTEXT.md` "Supply and purchasing".
>
> Guardrail: the engine is deterministic. No LLM participates in any quantity, date or ranking.

## Journey

Five actors. The system's job in every lane is the same: replace a person reading a list line
by line with a proposal that person accepts, rejects or adjusts.

### Whoever holds the upload permission - creates the demand

**Who this is remains an open debate and the build does not depend on settling it.** The system does
not yet help Project CS, so pinning the upload on them is premature; it may equally be purchasing
internally. What is certain is that someone uploads the sales orders, and that a change to an SO is
what triggers a change to a PO. So it is a **permission, not a person**, and assigning it is a
configuration act that can happen the week before go-live.

1. **They upload an extract.** Scope is derived from the file and then **bounded by what they own**:
   a holder whose permission covers only their own projects cannot restate beyond them, and rows
   beyond it are reported as out of authority rather than silently applied.
2. They see the same preview and confirmation as any other uploader, and the same per-row reasons
   for anything unresolved.

**Retail and dealer SO needs an owner too**, and had none in the first draft of this document. Retail
is roughly half the book and the plan is simply wrong without it.

### Josephine - the planner

Arrives from the sidebar, quarterly for planning and weekly for Mr Loo's report. Today she
opens a project's order inquiry, opens the outstanding SO book, opens the BRW report, and
reconciles them by eye.

1. **She uploads the whole open book** (outstanding SO and outstanding PO) as the reconciliation
   pass. Only her role may declare whole-book scope. The system already knows the products, the
   warehouses, the customers and their demand class, so she supplies nothing but the files and the
   scope she exported. It shows her what will change before anything commits.
2. **She opens the plan.** One screen: every product and location where the dated balance goes
   negative, worst first. She decides nothing yet.
3. **She opens one row and reads the Coverage Timeline** - opening stock, then each SO and each
   PO in date order with a running balance, grouped under month headings. The single decision
   here is: *do I believe this number?* She can answer it by looking, because every line names
   a document she recognises.
4. **She approves or rejects each suggested buy**, adjusting quantity or date where she knows
   something the system does not, with a reason. What she approves becomes Joey's work.
5. **At the end she holds** the Summary Order Report for Mr Loo: on-hand against committed
   across all products, shortages flagged, each traceable to its timeline.

### The step before Joey - the SO must be re-uploaded

Nothing reaches this system until the sales order is re-uploaded. The full sequence, because omitting the
middle step implies the system notices a project moving on its own:

1. Ziv flags a site delay to the salesperson, who relays it. Entirely outside the system, and the source
   flow already warns that a slow relay means stock arrives on the old schedule and becomes overstock.
2. The SO changes in AutoCount.
3. **The SO is re-uploaded** by whoever holds the permission. Until this happens the plan confidently
   describes a world that has moved on, and no exception exists.
4. Confirming the upload recomputes and diffs, producing the batch of exceptions.
5. Only now is there a queue for Joey to work.

**The honest limit:** the system is only as current as its last upload, and steps 1 and 2 are human relay it
cannot observe. That is an argument for uploading often, and it is the standing consequence of having no
AutoCount integration. It belongs on the screen, not in a footnote.

### Joey - creates the POs, and does not decide them

Mr Loo has already decided the quantity and the supplier, so this lane is a **worklist, not a second
decision point**. And with no AutoCount integration, the real work happens in two windows: our system
on one side, AutoCount on the other, keying POs one by one.

1. **She sees what has been decided**, grouped by supplier, with need-by, place-by derived from lead
   time, and last purchase cost.
2. **She marks each PO as keyed into AutoCount herself**, because nothing can detect it. The mark is a
   status pill using the shared component, and the column is **visible in the list and filterable** -
   the only question she has at the end of the day is what she has not done yet.
3. **A use-pool row appears in the worklist saying no PO is needed**, rather than being silently
   absent, so the list reconciles against Mr Loo's decisions one for one.
4. **When a project changes**, she does not re-read the PO book. Plan Exceptions are already waiting,
   each with the before and after timeline and proposed actions. Her decision per exception is approve,
   adjust or reject.

### Ms Tee - fulfilment

Arrives quarterly-to-monthly when a shipment is due, and whenever the supplier sends a file.

1. **She uploads the supplier's inventory status.** The system separates what is packed and
   loadable from what the supplier holds unfinished, and knows the volume of every item.
2. **She sets the capacity** - how many containers of what size - and gets a ranked Loading
   Plan: what to load, in what quantity, cut at the volume limit, with the deferred lines and
   the reason visible. Items blocked on production are listed separately as a different ask.
3. **She approves the plan.** One action sends the Supplier Notice on every channel the
   supplier is reachable on, and produces a document she can also paste into chat herself.
4. **She uploads the pre-load list or packing list.** The system reads every container block in
   the workbook and proposes, per line, which Supply PO line and which location it draws down.
5. **Her single decision per line is accept or reallocate.** Approving writes the SPO
   allocations, drops the PO's outstanding quantity, and makes the incoming stock visible to
   salespeople from that moment rather than after the SPO is keyed by hand.

### Mr Loo - decides the order quantity

Arrives at the Summary Order Report, weekly. Today it is a printed sheet whose
`TOTAL ORDER QTY` column is blank and filled in by hand in pen.

1. **He reads one row per item, network wide** - on hand, project demand, dealer outstanding,
   quantity on order, quantity in transit, and the shortfall.
2. **He opens any aggregate that he does not simply believe.** Project demand decomposes into
   which projects and which sales orders at which dates. Dealer outstanding decomposes into which
   dealer, which sales order, and **how long they have been waiting** - which is the column the
   printed sheet has no room for, and the reason two units can be more urgent than two hundred.
3. **He picks the supplier**, from candidates each showing last PO cost, **last PO date**, last
   incoming cost, and the variance between the two. Last PO date is what tells him whether an
   item is moving at all; a cheap quote from 2023 is a guess, not a price.
4. **His single decision is the order quantity**, and it is routinely **above** the shortfall.
   The system states what his number means - cover gained, cash committed, container volume added,
   spare stock created - and keeps its own figure beside it. It does not correct him.
5. He also approves price and PO later in Joey's lane, and asks where a container is, which is out
   of scope this release.

### The supplier

Receives the notice before it is asked for the order, so production and packing are ready when
the PO lands. Sends inventory status, pre-load list and packing list; never uses the system.

---

## Group A - Demand and supply feed

**AC-A1** GIVEN an AutoCount outstanding-SO extract, WHEN a holder of the upload permission submits it,
THEN the system
maps its columns via the alias table, resolves product, warehouse, customer and demand class,
and writes `sales_orders` / `sales_order_lines` with a per-line `required_date`.

**AC-A2** Scope is **derived from the file, not asked for**. The importer reads which projects,
customers and date span the file covers and states it in words on the preview; restatement closes only
lines inside that derived scope. Asking someone to declare a scope while they are simply importing a
file makes the system's problem into the user's problem. An override exists for the one case the
contents cannot reveal (a genuinely partial export of a single project) and is not the normal path.

**AC-A2a** The derived scope is bounded by the uploader's authority. A holder whose permission covers
only their own projects cannot restate beyond them even if the file spans more; those rows are
reported as out of authority rather than silently applied.

**AC-A2b** Upload uses the **shared attachment upload component** (`FileUploadZone`, the one resource
attachments use). No new hand-rolled drop surface: the codebase already carries several and this adds
none.

**AC-A3** Nothing commits before a preview. The preview states the derived scope in words before it
states any count. The preview states counts for new, quantity-changed,
date-changed, will-be-closed, and out-of-scope-untouched, and requires explicit confirmation.

**AC-A4** A line present in a previous upload and absent from this one, **within scope**, is
closed - not deleted. Its history remains readable.

**AC-A5** Uploading the `MARYAM TUJU RESIDENCE` file with scope "one project" leaves every
other project's committed demand untouched. This is a test, not a hope.

**AC-A6** Outstanding-PO extracts follow AC-A1 to AC-A4 identically, writing `purchase_orders` /
`purchase_order_lines` with `expected_date`.

**AC-A7** Every upload retains its original file and produces per-row outcomes (success, skip
with code, failure with reason), reusing the existing import-job machinery.

**AC-A8** An upload is idempotent: submitting the same file twice with the same scope produces
no second set of changes.

## Group B - Coverage Timeline

**AC-B1** For one product at one **fulfilment pool** (a site and the bins under it), the timeline
lists opening on-hand, then every open committed-demand line at its `required_date` and every open
supply line at its `expected_date`, in date order, with a running balance after each event.

**AC-B1a** Pool membership is a stored, editable pointer per location, not a parsed code. It is
seeded from Sorento's convention (`SITE-SUFFIX` points at `SITE`; a code with no suffix points at
itself), and a shared pool's quantity is available to every location pointing at it. A pool never
reaches a location pointing elsewhere.

**AC-B1a-i** Whether a location's stock counts as available at all is a **separate** configurable
flag, defaulting to **true for every location**. Nothing is excluded by naming convention. One flag
cannot express both "sellable" and "may cover another location's demand", and conflating them
reintroduces the per-warehouse defect in AC-B1c.

**AC-B1a-ii** A client whose location codes follow no recognisable convention can still use the
engine by repointing pool membership on the warehouse screen. No code change, no deploy.

**AC-B1b** Each demand line resolves against a source preference: its own customer bin, then the
same-site shared pool, then another customer's bin behind an allocation claim, then a purchase.
These are the existing `projects.so_line_allocations.source_type` values `own`, `brw`, `other_project`,
`order`.

**AC-B1c** A purchase is recommended only when no existing source covers the line. The regression
case is item `SRTWT7408`: demand 67 against customer bins with 4,397 in the shared pool must
produce "use the pool", never a buy of 67.

**AC-B1d** Cross-site cover is never netted silently. Where another site holds stock, it is surfaced
as a transfer proposal carrying its cost and lead time, for a person to accept.

**AC-B2** Each event names its source document in human-readable form - SO number, PO number,
customer or project name. No UUID appears.

**AC-B3** Months are display grouping only. Changing the grouping cannot change any balance.

**AC-B4** Supply dated after a demand event does not offset it. A PO with ETA 25 Aug against an
SO due 3 Aug produces a shortfall, and the timeline shows both rows so the 22-day gap is
visible.

**AC-B5** The horizon is configurable per tenant in months. Events beyond it are excluded and
the exclusion is stated on screen, never silent.

**AC-B6** The timeline is computed, never stored, so it cannot go stale against the documents
it summarises.

**AC-B7** The timeline **extends the existing `ReorderExplanationDialog` on `/scm/reorder`**. It is not
a new page. A second planning UI beside the first is the defect this avoids.

**AC-B8** Decision-making starts from the **list**, not from a product. A row is opened from the
results grid, and the dialog carries **previous and next** so a planner walks the shortfall list
without closing it.

**AC-B8a** A planning run can be scoped to **specific products**, not only to warehouses. The manual run
modal takes warehouses and budget today (its source notes the legacy `buy_scope` was removed); a
`product_codes` multi-select is added beside the warehouse picker using the same `SearchableMultiSelect`.
**Empty means all products**, so existing behaviour and the scheduled daily run are unchanged. This is an
explicit product list, not a reinstated category filter.

**AC-B9** New views arrive as **tiles on `ReorderStatTiles`** beside the existing Buy, Stock
allocation and Cash impact, so a count is visible without navigating. Plan exceptions and the PO
worklist are tiles, not pages.

## Group C - Buy plan and approval

**AC-C1** The shortfall is the first event where the running balance falls below the floor. The
recommendation carries both the quantity and that event's date as the need-by date.

**AC-C2** A place-by date is derived as need-by minus resolved lead time, and is shown alongside
need-by. Where place-by is already in the past, the row is flagged as late rather than silently
recommended.

**AC-C3** Quantity is rounded by the existing MOQ and order-multiple logic, and the pre-rounding
figure remains visible.

**AC-C4** A continuous-demand SKU produces byte-identical output to today's engine. This is
asserted against the existing golden set, not inspected by hand.

**AC-C5** Josephine can approve, adjust with a reason, or reject each recommendation, reusing
the existing decision and override overlay.

**AC-C6** Approved recommendations group by supplier into draft Supply POs. A draft PO is not
supply and does not appear in `scm.on_order_v`.

**AC-C7** Last purchase cost for the item and supplier is shown on the buy row, sourced from
prior PO lines.

## Group C2 - Summary Order Report and the order-quantity decision

**AC-C2.1** One row per product, network wide, carrying on hand, project demand, dealer
outstanding, quantity on order, quantity in transit, shortfall, suggested quantity, chosen order
quantity, and the chosen supplier.

**AC-C2.2** Quantity on order and quantity in transit are **separate columns**, sourced from open
Supply PO lines and from inbound shipment lines respectively. Their sum is what the net position
uses; the split is what is displayed, because only the on-order half is still negotiable.
`scm.on_order_v` today reads only PO lines, so the two are currently indistinguishable.

**AC-C2.2a** Every row is clickable, and each aggregate opens **behind an information icon** rather
than rendering inline. The list carries only what is needed to decide. Preventing information fatigue
is a requirement, not a preference.

**AC-C2.3** Project demand opens to show, per contributing line: project name, SO number, quantity
and required date. The month profile shown on the row is derived from these lines and never
retyped by a person.

**AC-C2.4** Dealer outstanding opens to show, per contributing line: dealer name, SO number,
quantity, and **days outstanding**. Ageing is sorted worst-first, because a small quantity that has
waited 214 days outranks a large one raised last week.

**AC-C2.5** Supplier is a selectable choice, not a fixed value. Each candidate shows last PO cost,
**last PO date**, last incoming cost, the variance between ordered and incoming cost, on-time rate
and lead time. A candidate that has never delivered this item says so rather than appearing merely
cheap.

**AC-C2.6** A stale last PO date is surfaced as such. An item last bought years ago is flagged, and
that flag is what distinguishes a fast mover from a dead line.

**AC-C2.7** The chosen order quantity may exceed the shortfall, and doing so is not a warning
state. On entry the system states: shortfall covered, spare created and where it lands, resulting
months of cover, cash committed, and container volume added.

**AC-C2.8** The engine's suggested quantity stays visible beside the chosen quantity, and the
difference is recorded with actor and time, so a larger number is a decision on the record and not
an untraceable override.

**AC-C2.9** The report is reproducible for a past week. What Mr Loo saw when he decided is
recoverable, or the decision cannot be reviewed.

## Group C3 - Cost capture

**AC-C3.1** Ordered cost is read from `purchase_order_lines.unit_cost` with its currency.

**AC-C3.2** Incoming cost is captured from the packing list at the moment an SPO allocation is
approved and stamped on the inbound shipment line. The column exists and is populated in 0 of
1,015 existing rows, and the table has **no currency column**, so both the write and a currency
migration are in scope. (Met since 17 Aug 2026: the currency column landed with S3b and the
Excel packing-list ingest now fills both columns at upload. Contract and known limits:
`scm-proforma-invoice-acceptance-criteria.md` AC-P5.)

**AC-C3.3** Ordered cost is never overwritten by incoming cost. The variance between them is a
first-class output, since a supplier whose incoming cost drifts above its ordered cost has repriced
after we committed.

**AC-C3.4** Both figures are labelled ex-works in the supplier's currency. Neither is presented as
a landed cost, because freight and duty are not in the purchase order.

**AC-C3.5** Cost sits beside on-time rate and lead time wherever a supplier is compared. Cost alone
cannot answer whether to change supplier.

## Group D - Change propagation

**AC-D1** A change to committed demand is recorded as a delta to dated demand events. No verb
vocabulary is stored as behaviour.

**AC-D2** After a delta, the affected product and **fulfilment pool** are recomputed and the new plan
is diffed against placed supply, producing typed Plan Exceptions.

**AC-D2a** Exceptions are generated **as a batch on confirmation of a re-uploaded SO**, not as ad-hoc
signals arriving individually. The re-upload is the trigger that exists today; a project-sales amendment
produces the same deltas through the same service, so that work merging adds a producer and changes
nothing else.

**AC-D2b** The upload preview's counts and the resulting exceptions are the same facts at two stages,
and must reconcile. A delta becomes an exception **only** when it disagrees with supply already placed,
so the exception count is normally far smaller than the delta count, and that reduction is the value of
the screen.

**AC-D3** Exception types cover at minimum: shortfall now earlier than planned, supply now
early against a delayed commitment, supply now permanently surplus, and supply at the wrong
location.

**AC-D4** Every exception shows the before and the after timeline side by side.

**AC-D5** Every exception carries at least one proposed action, and where a reallocation is
possible, the candidate order it would move to, with that order's need-by date.

**AC-D6** No placed Supply PO is amended without explicit human approval. Approval is recorded
with actor and time.

**AC-D7** Approving a reallocation writes an allocation decision. It does not amend a purchase
order.

**AC-D8** The eight change cases in the source flow are covered by a test table asserting each
produces the expected exception type, with no branch in the engine keyed on the verb.

**AC-D9** Every exception carries the item's **reading** alongside the arithmetic: lifecycle
(`products.is_discontinued`), velocity (`scm.item_classification` ABC and XYZ), business
(`market_segments` demand class), and last PO date. All four already exist; none is newly computed.

**AC-D10** Proposed actions are **ordered by that reading**, not by quantity. The regression table
asserts the inversion: identical arithmetic on a discontinued C/Z retail item proposes *keep the PO
and take the stock into the pool* first, where an active A/X project item proposes *reallocate*, and
an active C/Z retail item proposes *push the ETA out*.

**AC-D11** A surplus of a **discontinued** item is never proposed for cancellation or ETA deferral as
the first option. It is the last stock of that product obtainable, and deferring risks the supplier
closing the line.

**AC-D11a** Proposed actions cover, at minimum: **relink to another SO**, **change the allocated
location** (including release to the shared pool, the flow's "deallocate back to BRW"), **split the line
so only part of it moves**, push the supply ETA, and accept with a reason.

**AC-D11b** A split must sum to the original quantity, and each part carries its own source and reason.
A partial change was unrepresentable before this and is the most common real shape.

**AC-D12** The reading is displayed, not merely applied. Each signal shows its value and its source
field, so the person approving can disagree with the reasoning and not only with the outcome.

## Group D2 - Upload authority

**AC-D2.1** Upload scope is bounded by role. A Project CS user's scope is forced to projects they
own; only planning may declare whole-book scope.

**AC-D2.2** A restatement can never close a line outside the uploader's authority. This is asserted
as an RBAC test, not left to the UI.

## Group E - Supplier inventory and Loading Plan

**AC-E1** The supplier inventory upload distinguishes packed, loadable stock from stock the
supplier holds unfinished, and carries per-unit volume.

**AC-E2** Only packed stock is eligible for a Loading Plan. Unfinished stock is listed
separately as needing production, with the quantity, so Ms Tee can ask for it.

**AC-E3** Capacity is expressed as container count and container size, resolving to a volume
limit. Container sizes are configurable per tenant.

**AC-E4** Outstanding PO lines are ranked by the Fulfilment Priority policy and filled until
capacity is reached. Partial fill of a line is permitted.

**AC-E5** Every deferred line states why it was deferred - over capacity, or no packed stock.

**AC-E6** Changing the container count re-runs the plan without re-uploading anything.

**AC-E7** The ranking factors and their contribution are visible per line. A rank a planner
cannot decompose is not acceptable.

## Group E2 - PO creation worklist

**AC-E2.1** The worklist shows what Mr Loo decided, not a fresh decision: quantity, supplier and who
decided it with a timestamp.

**AC-E2.2** A manual **keyed-into-AutoCount** status per row, set by the person doing the keying because
nothing can detect it. Values at minimum: not keyed, keying, keyed.

**AC-E2.3** The status uses the **shared status-pill component**. No new colour vocabulary.

**AC-E2.4** The column is visible in the list **and filterable**. Filtering to not-keyed is the primary
use of the screen.

**AC-E2.5** A use-pool decision appears in the worklist stating that no PO is needed, rather than being
absent, so the worklist reconciles one-for-one against the decisions.

## Group F - Supplier Notice

**AC-F1** Approving a Loading Plan produces one Supplier Notice record.

**AC-F2** The notice renders a bilingual document in the shape the supplier already uses:
model, quantity to pack, volume, target departure, and the needs-production items separately.

**AC-F3** The notice sends by email to the supplier's address, and is downloadable so Ms Tee can
send it by chat herself.

**AC-F4** Chat is declared as a channel on the notice and lights up when a WeChat channel exists
in the Respond workspace, with no change to the trigger, the content or the record.

**AC-F4a** Adding a channel changes no existing send. Template sends already carry
`template.channel.respond_channel_id`, so WeChat templates point at the WeChat channel row and existing
WhatsApp templates keep pointing at theirs. Free-text sends pass no channel at all today and are routed
by the contact's own channel. Workspace key resolution sits above channel and is untouched.

**AC-F4b** Guarded by a regression test, not by reasoning: an existing WhatsApp send produces a
byte-identical payload after a WeChat channel row exists. If that test fails the change is wrong.

**AC-F4c** New work is the supplier-to-Respond-contact link and one loading-notice template row per
channel.

**AC-F5** Every send attempt writes an integration log on success **and** on failure. A 401
against wrong credentials is logged as an attempt, not swallowed.

**AC-F6** The notice states what was sent, to whom, on which channel, and when.

## Group G - Packing list and SPO allocation

**AC-G1** The pre-load and packing-list importer reads a workbook containing several container
blocks and produces one inbound shipment per block with its lines. The 5-block, 34-line sample
imports as 5 shipments.

**AC-G2** A pre-load list with blank container number and blank bill of lading imports
successfully. Neither field is required.

**AC-G3** Duplicate detection does not rely on container number, since it is blank at pre-load
stage. Re-uploading the same pre-load list creates no second set of shipments.

**AC-G4** For each shipment line the system proposes a Supply PO line and a warehouse, ranked by
Fulfilment Priority, with the reason and the alternatives shown.

**AC-G5** `spo_allocations` carries a nullable `po_line_id`. Nullable because existing rows have
no PO, and because stock can arrive against no PO. Today **all 860 live rows are unlinked**, which
is why supply and ordered are never netted against each other (see AC-G6a).

**AC-G6** REVISED 6 Aug 2026, because supply is now the SPO allocation rather than the purchase
order. Approving allocations does two things in one action: the new allocation makes
`scm.on_order_v` (INCOMING) **rise**, and advancing the PO line's received quantity makes
`scm.po_ordered_v` (ORDERED) **fall**. On screen the quantity moves from the Ordered tile to the
Incoming tile, and the Coverage Timeline gains a dated arrival in the same action. The earlier
wording said `on_order_v` falls, which was true only while that view read purchase orders.

**AC-G6a** Because approving an allocation writes BOTH the allocation and the PO line's received
quantity, a linked allocation is counted exactly once: as incoming supply, and no longer as
ordered. An UNLINKED allocation (`po_line_id IS NULL`, every historical row) leaves the ordered
figure overstated by whatever it shipped against, which is the stated cost of the 6 Aug decision
and is visible rather than hidden. What must never happen is the reverse: adding the ordered
figure into the balance, which would double every shipped order.

**AC-G7** A shipment line may be split across several PO lines and locations, and the split must
sum to the shipped quantity.

**AC-G8** Incoming stock is visible to salespeople from the moment allocations are approved, not
from the goods-received date. This is now structural rather than a feature to build: the
allocation IS the supply, so there is no path by which an approved allocation is invisible.

## Group H - Fulfilment Priority policy

**AC-H1** Priority is a weighted policy row, per tenant, not a rule in code.

**AC-H2** The seeded default ranks by outstanding customer demand first (project, then retail,
then nothing owed) and by PO document sequence within each demand band. Superseded 2026-08-17 by
the captain's decision (`decision-loading-plan-demand-source.md`, gap G1a): the original seed
reproduced the manual answer (sequence only) with demand weighted 0.0; migration 374 raises
demand to 3.0. A line owed to nobody scores demand 0.0 (present), never absent.

**AC-H3** The weighting is a policy row (`scm.priority_policy`) editable in the FE; need-by-date
still ships weighted 0.0 by default.

**AC-H4** Switching weights shows a side-by-side preview of which lines change rank and by how
much, before committing.

**AC-H5** The same policy is applied to Loading Plan ranking and to SPO allocation ranking. Two
policies for the two moments is a defect.

**AC-H6** Adding a demand class is a `market_segments` row plus a weight. It is never a schema
change.

## Group I - Configurability

**AC-I1** Column aliases live in a seeded table keyed by document type, canonical field, alias
and locale, so `型号` and `ITEM CODE` are two aliases of one field.

**AC-I2** A plain admin screen lists and edits aliases. Diagnosing a failed import does not
require a database session.

**AC-I3** Onboarding a client with different export headers is data entry plus a re-run, not a
deploy.

**AC-I4** Per-tenant parameters at minimum: planning horizon, safety-stock method and
parameters, container sizes, priority weights, demand classes and their weights, lead-time
source.

## Group J - Core and module boundary

**AC-J1** Core, surviving module uninstall: `sales_orders`/`_lines` including `required_date`,
`purchase_orders`/`_lines`, `inbound_shipments`/`_lines`, `spo_allocations` including
`po_line_id`, suppliers, import jobs, supplier notices.

**AC-J2** Module (`scm` schema), dropped on uninstall: every policy and every suggestion,
including the new priority policy, loading plans and plan exceptions.

**AC-J3** After uninstalling `scm`, allocations, shipments, POs, SOs and sent notices are all
intact and readable, and Ms Tee can key an SPO by hand exactly as she does today.

**AC-J4** Every new route sits behind the existing module guard and new permission slugs. An
existing role without those slugs sees no new navigation and receives 403 on the new APIs.

**AC-J5** Additive columns on shared tables are nullable or carry a server default, so the
migration is safe on live data.

## Group K - Explicitly out of scope

Named so nobody assumes them. Each is a real item from the source flow.

- **MOQ group-purchase broadcast.** Unresolved in the source: who runs the broadcast and how
  long we wait for replies before ordering anyway. An open-ended wait is how MOQ items stall.
  Needs a decision before it can be built.
- **Forward forecast from project sales** (2027 delivery quantities). Collected ad hoc today.
  Needs a cadence, an owner and a home before it is worth a screen.
- **Container status tracking from shipper and CIDB websites.** External scraping, no stable
  contract.
- **Packing list output variants** for salespeople and customs. The importer lands here; the
  three export templates do not.
- **Material cost basis for founder costing.** Unresolved: latest, average or landed. Landed
  needs freight and duty, which are not in the PO. Needs Mr Loo.
- **F-GRN for extra quantity found in a container.** Downstream of goods-received.
