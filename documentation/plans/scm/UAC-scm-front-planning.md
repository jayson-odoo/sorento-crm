# UAC: SCM Front Planning

**Status:** FINALIZED, grilled and pre-code, 16 August 2026

**Plan:** `documentation/plans/scm/PLAN-scm-front-planning.md`

**Scope:** Project Fulfilment Planning through the Product and Location SCM plan views.

These criteria are the binding contract. Each criterion is independently verifiable. Terms and
formulas have the meanings defined in the linked plan.

## Guided journey

1. **J01 - Accept demand.** Customer Service starts from the accepted Project PO and delivery
   schedule; the system already knows the project, products, quantities, dates, and locations.
2. **J02 - Release.** CS reviews the prefilled release proposal and exports the AutoCount worksheet.
3. **J03 - Reconcile.** CS uploads the resulting SO, resolves any header or line exception, and
   reaches one whole-SO **Needs CS review** state without creating purchasing demand.
4. **J04 - Compose supply.** CS opens one side sheet showing dated location SPO supply, eligible
   Reserve, explicit Borrow evidence, Buy residual, warnings, and reasons for every line.
5. **J05 - Confirm once.** CS confirms the entire balanced Project SO in one atomic action.
6. **J06 - Hand off Buy.** Purchasing receives only the confirmed, unplaced Buy residual in Order
   Inquiry and can trace it to the decision.
7. **J07 - Plan by product and channel.** The buyer works up to two rows per product, Retail for
   BRW member locations and Project for BRW-xx project-location members, with supplier constraints
   applied once to each actionable product-channel row.
8. **J08 - Drill by location.** The buyer switches to Location grain to inspect or work the same
   frozen member-location rows; the run keeps only one actionable grain.
9. **J09 - Key and follow through.** The chosen product-channel quantity is split through the
   existing recommendation allocation, keyed once, and carried through placement and receipt.

The successful journey ends with balanced SO lines, Buy-only Order Inquiry demand, reproducible
Product and Location views, and one location split linked into the existing fulfilment ledger.

### Journey traceability

| Journey step | Acceptance criteria |
|---|---|
| J01 | AC-A01, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J02 | AC-A01, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J03 | AC-A01 through AC-A04, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J04 | AC-B01 through AC-B13, AC-G02, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J05 | AC-C01 through AC-C08, AC-G01, AC-G03, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J06 | AC-D01 through AC-D06, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J07 | AC-E01 through AC-E07, AC-F01, AC-F03 through AC-F07, AC-F09 through AC-F12, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J08 | AC-F01 through AC-F10, AC-F12, AC-G04, AC-G06, AC-H01 through AC-H04 |
| J09 | AC-F12, AC-G04 through AC-G06, AC-H01 through AC-H04 |

## Group A: Release and reconciliation

### AC-A01 [E2E][J01][J02][J03] Accepted demand reaches one review journey

Given an accepted Project PO version and delivery schedule, when CS creates the release proposal,
exports the AutoCount worksheet, uploads the resulting SO, and follows normal application
navigation, then the Project SO is reconciled and opens in Project Fulfilment Planning without
creating purchasing demand before confirmation.

### AC-A02 [BE][J03] Header and line reconciliation is mandatory

Given a Project SO, when reconciliation completes, then its core SO header is linked and each
Project SO line has exactly one core SO-line link; a missing, duplicate, or ambiguous link prevents
the SO from becoming confirmable and returns a human-readable line number and item code.

### AC-A03 [FE][J03] The whole SO has one pre-confirmation state

Given a reconciled but unconfirmed Project SO, when any user views its header, list row, or side
sheet, then the whole SO reads **Needs CS review** and no line is labeled partially confirmed,
confirmed, or purchasing-ready.

### AC-A04 [BE][J03] Pre-confirmation demand is excluded

Given any Project SO in **Needs CS review**, when Order Inquiry and SCM demand readers run, then
all lines from that SO contribute zero purchase requirement.

## Group B: Deterministic coverage and suggestions

### AC-B01 [BE][J04] The line balance uses current open quantity

Given a reconciled Project SO line, when its suggestion is calculated, then the starting quantity
is the core SO line's current open fulfilment quantity in the line UOM, not the original customer
quantity and not a value reduced again by a downstream reader.

### AC-B02 [BE][J04] Only timely location SPO covers demand

Given inbound SPO quantities for a product and line location, when coverage is calculated for a
required date, then location availability is stock plus SPO incoming by that date minus outstanding
SO at that location; no SPO-to-SO-line allocation is required or inferred.

### AC-B03 [FE][J04] Late incoming is advisory

Given matching inbound that arrives after the required date, when CS opens the side sheet, then it
is labeled advisory for that date and contributes zero coverage at that date.

### AC-B04 [BE][J04] Suggestions are deterministic

Given identical frozen stock, claims, incoming, classification, reorder level, dates, and SO data,
when the suggestion is calculated twice, then timely SPO coverage, Reserve, Borrow candidates, and
Buy are identical and no LLM or nondeterministic optimizer supplies a quantity.

### AC-B05 [BE][J04] Hot-selling uses existing ABC facts

Given a product, when Reserve eligibility is calculated, then it is dealer hot-selling exactly
when a current `scm.item_classification` row has ABC A at an active, available warehouse whose
stored `segment` is `dealer`; `computed_at` is evidence rather than a freshness gate, and when no
classification row exists for any qualifying warehouse the sheet shows **Retail classification
unavailable** rather than inferring a class.

### AC-B06 [BE][J04] Hot-selling Reserve protects dealer and BRW stock

Given a dealer hot-selling product, when Reserve is proposed, then dealer-facing free stock
contributes zero and the maximum BRW Reserve is
`max(BRW free unclaimed stock - coalesce(BRW per-location reorder level, 0), 0)`.

### AC-B07 [BE][J04] Non-hot-selling Reserve stays inside its boundary

Given a product that is not dealer hot-selling, when Reserve is proposed, then only free
unclaimed stock in the SO's own fulfilment location or shared BRW contributes; stock elsewhere
or committed to another SO is presented as Borrow, not Reserve.

### AC-B08 [T][J04] The hot-selling worked case is fixed

Given a hot-selling product with need 70, dealer-facing free stock 50, BRW free unclaimed stock
120, and BRW reorder level 80, when the proposal is calculated, then Reserve is 40, dealer-facing
Reserve is 0, and the Borrow-or-Buy residual is 30.

### AC-B09 [FE][J04] Borrow evidence and reason are mandatory

Given CS selects Borrow, when the side sheet validates the line, then it shows the donor location
or SO/project, quantity, current donor shortfall or days-of-cover impact, and a required reason;
the Confirm action remains disabled until a reason is entered.

### AC-B10 [BE][J04] Borrow has no second approver

Given a valid Borrow selection and reason, when the authorized CS actor confirms the Project SO,
then that confirmation is sufficient to commit Borrow and no intermediate request, donor-CS
acceptance action, or second approver is required; cross-project Borrow may write its audit claim
directly in the terminal accepted state in the same transaction.

### AC-B11 [E2E][J04] Discontinued Buy is allowed with control

Given committed customer demand for a discontinued product and a positive Buy residual, when CS
reviews the line, then a visible warning and required reason are shown; after the reason is
entered, the SO may be confirmed and the Buy residual reaches Purchasing without automatic
substitution.

### AC-B12 [BE][J04] Every proposal balances

Given a proposed line, when the engine returns it, then all quantities are non-negative and
`open quantity = timely SPO coverage + Reserve + Borrow + Buy`; otherwise the line is an
explicit calculation error and cannot be confirmed. Timely SPO coverage contains no stock because
stock appears only as Reserve or Borrow.

### AC-B13 [BE][T][J04] Confirmed cover is unavailable to later demand

Given dated location supply covers one SO or Reserve or Borrow is confirmed for it, when a later CS
proposal or replenishment calculation reads the same product and location, then outstanding demand
and confirmed claims reduce availability and the quantity cannot be consumed a second time.

## Group C: Atomic Project SO confirmation

### AC-C01 [E2E][J05] One action confirms all lines

Given a Project SO with multiple valid balanced lines, when authorized CS presses **Confirm
Project SO** once, then every line becomes committed in one transaction and the SO leaves
**Needs CS review**; there is no per-line confirmation action or durable partial state.

### AC-C02 [BE][J05] One invalid line rolls back the SO

Given one line becomes stale, over-allocated, unbalanced, unmapped, or invalid while other lines
remain valid, when confirmation is attempted, then no decision, allocation, claim, or inquiry row
from that attempt is committed and every failing line is returned by line number and item code.

### AC-C03 [BE][J05] Confirmation rechecks authoritative facts

Given a side sheet was opened earlier, when confirmation begins, then the service re-reads open
quantity, line mapping, location SPO quantities and dates, free unclaimed stock, claims, ABC facts,
reorder levels, donor impact, and product lifecycle before writing.

### AC-C04 [BE][J05] One active revision represents the SO

Given a confirmed Project SO, when its decision is read, then exactly one active SO-level revision
contains one snapshot for every SO line and each snapshot records all balance components and
evidence identifiers.

### AC-C05 [BE][J05] Concurrent confirmations cannot double-claim

Given two actors attempt to confirm competing uses of the same stock or dated location supply,
when the transactions race, then at most one commits the disputed quantity and the other returns
a refresh-required conflict without partial writes.

### AC-C06 [E2E][J05] Material change reopens the whole SO

Given a confirmed Project SO, when quantity, required date, product mapping, core line link, or a
material supply fact changes, then the active revision is superseded or challenged, the whole SO
returns to **Needs CS review**, and no line remains independently confirmed.

### AC-C07 [BE][J05] Existing execution is preserved on reconfirmation

Given a prior Buy has been placed or received, when a later revision lowers or removes need, then
placed or received supply remains in the ledger and an actionable exception is created rather
than deleting history or making the quantity available to buy again.

### AC-C08 [BE][J05] Authorization and company isolation apply to the transaction

Given an actor lacks the required CS permission or belongs to another company, when confirmation
is attempted, then it is denied and no cross-company SO, stock, incoming, decision, or inquiry
fact is disclosed or changed.

## Group D: Buy-only Order Inquiry

### AC-D01 [BE][J06] Inquiry is created only at successful confirmation

Given a Project SO is published or reconciled but not confirmed, when its lifecycle advances,
then no standard Order Inquiry demand row is created; when atomic confirmation commits, inquiry
rows are created or refreshed in that same transaction.

### AC-D02 [BE][J06] Inquiry quantity equals confirmed Buy

Given a confirmed decision line, when `buy_qty > 0`, then exactly one active unplaced inquiry row
exists with that quantity; when `buy_qty = 0`, no active purchase row exists for the line.

### AC-D03 [T][J06] Coverage never enters purchasing demand

Given any amounts of timely SPO coverage, Reserve, Borrow, or late incoming, when Order Inquiry
and SCM readers run, then those amounts contribute zero demand and
only the confirmed Buy residual is counted.

### AC-D04 [BE][J06] Inquiry does not net supply again

Given a confirmed Buy row, when it is read into SCM, then the reader uses its current unplaced
quantity directly and does not repeat pre-order, inbound, stock, or customer-delivery netting.

### AC-D05 [BE][J06] Handoff is idempotent across retries and revisions

Given confirmation is retried or a decision is superseded, when inquiry rows are refreshed, then
there is at most one active unplaced row for the active decision line, the old row remains
auditable, and placed or received quantities are not duplicated.

### AC-D06 [FE][J06] Purchasing can trace Buy to its decision

Given a buyer expands a Project contribution, when the inquiry row is shown, then the UI links it
to the human-readable Project SO, line number, item code, required date, and decision revision,
without displaying a UUID.

## Group E: Deterministic channels and Product grain

### AC-E01 [BE][J07] Channel derives from the SO market segment

Given an SO market segment, when the order is imported or a Project SO is published, then
`project`, `projects`, and `contract` map to persisted `sales_orders.demand_class = project`, every
other stated value maps to `retail`, and no AI, salesperson, warehouse, or free-text inference
participates.

### AC-E02 [BE][J07] Location disagreement is explicit

Given persisted demand class and location disagree, when planning runs, then a Project order
outside a BRW-xx project location or a Retail order outside BRW becomes an exception row and is
never reclassified by location; an absent market segment is a data-quality exception rather than a
third demand class.

### AC-E03 [FE][J07] Product grain is Product x Channel

Given a frozen SCM run containing multiple locations and channels for one product, when **Plan
grain: Product** is selected, then the product has at most two actionable rows: Retail aggregates
BRW member-location rows and Project aggregates BRW-xx project-location rows; exceptions are shown
separately and never form a third channel row.

### AC-E04 [BE][J07] Project demand is confirmed unplaced Buy

Given Project SO decisions in mixed lifecycle states, when Product grain is built, then Project
outstanding quantity is the sum of member project-location rows, including current confirmed Buy
not yet placed, cancelled, or otherwise discharged; unconfirmed, Reserve, Borrow, covered incoming,
and already placed quantity are excluded from the Buy handoff.

### AC-E05 [BE][J07] Firm Project Buy bypasses reorder suppression

Given positive confirmed unplaced Project Buy and Retail demand below its reorder trigger, when
the product row is calculated, then Project Buy remains in raw product requirement and cannot be
suppressed by the Retail reorder level.

### AC-E06 [BE][J07] Supplier constraints are applied once

Given member location rows for one product-channel row, when its suggested quantity is calculated,
then SO outstanding, PO, timely SPO incoming, stock, reorder level, and unrounded suggested need
are summed first, and MOQ and order multiple are applied once to that product-channel row.

### AC-E07 [FE][J07] Product evidence is drillable

Given a product row, when Project or Retail is expanded, then the buyer can trace Project to SO
lines and decision/inquiry revisions and Retail to location stock, velocity, incoming, reorder,
and allocation evidence.

## Group F: Dual plan grains and allocation

### AC-F01 [FE][J07][J08] Both selectors remain distinct

Given the buyer plan, when its controls render, then it offers **Plan grain: Product / Location**
and separately offers **Planning mode: Auto / Manual**; choosing either control does not rename,
hide, or mutate the other vocabulary.

### AC-F02 [E2E][J08] Location grain remains selectable

Given a frozen run with `decision_grain = location`, when **Plan grain: Location** is selected,
then the same member-location recommendations, decisions, overrides, net positions, reorder levels,
and allocation evidence remain actionable; Product grain has not retired or replaced them.

### AC-F03 [BE][J07][J08] Both grains share one frozen input set

Given Product and Location views for a run, when their evidence is inspected, then both use the
same company, as-of time, demand, stock, incoming, policy, supplier facts, and source revision.

### AC-F04 [BE][J07][J08] Product reorder level is a sum

Given per-location reorder levels for a product, when Product grain is calculated, then each
product-channel row sums `coalesce(location level, 0)` over its member locations and the two channel
rows together sum all location levels; absent rows and NULL values contribute 0, and a product-wide
NULL-warehouse row is not chosen as a competing winner.

### AC-F05 [BE][J07][J08] Location mode keeps location levels

Given the same product, when Location grain is calculated, then each row reads its own
per-location reorder level with NULL treated as 0 for this feature; no product-level sum is
written back over those rows.

### AC-F06 [FE][J07][J08] There is no level worklist state

Given absent or NULL location levels, when either grain renders, then no inferred winner,
**Needs level** state, or buyer level-convergence worklist is introduced by this feature.

### AC-F07 [BE][J07][J08] Product-channel rows sum their member locations

Given a frozen product and channel, when Product grain is calculated, then SO outstanding, PO, SPO
incoming, stock, reorder level, and pre-constraint suggested need equal the sums of the channel's
member location rows from the same run.

### AC-F08 [FE][J08] Location drill explains the product-channel row

Given either plan grain, when a buyer opens a product-channel row, then the UI shows its member
locations, each summed input, the once-rounded suggested quantity, the chosen quantity, and the
chosen quantity's split back to locations.

### AC-F09 [BE][J07][J08] Exactly one grain is actionable per run

Given a run has no saved decisions, when the buyer first saves in Product or Location grain, then
that grain is locked as `decision_grain`; Product uses product-channel `order_summary_row`
decisions, Location uses existing recommendation decisions and overrides, and PO worklists ignore
the other grain.

### AC-F10 [E2E][J07][J08] A decided run cannot change actionable grain

Given the first Product or Location decision has been saved, when a buyer tries to make the other
grain actionable for that frozen run, then the change is rejected and all existing decisions and
overrides remain immutable; the buyer must create a new current run with a new frozen snapshot,
and no second purchasing action is created from the old run.

### AC-F11 [T][J07] Product-channel rounding is demonstrable

Given two member locations in one channel each contribute unrounded need 1 and the supplier
multiple is 10, when Product grain is calculated, then the actionable product-channel row sums need
to 2 and rounds once to suggested quantity 10; it does not round each member location first.

### AC-F12 [BE][T][J07][J08][J09] The chosen split is durable and balanced

Given a buyer saves a chosen quantity on a Product x Channel row, when its PO worklist split is
persisted, then the split reuses that row's existing recommendation allocation output, stores only
the member-location quantities needed for replay, and those quantities sum exactly to the chosen
quantity.

## Group G: Audit, lifecycle, and usability

### AC-G01 [BE][J05] Decision evidence is immutable and attributable

Given a confirmed decision, when it is audited later, then the actor, timestamp, SO revision,
line quantities, incoming references, stock sources, ABC and reorder evidence, donor impact,
reasons, warnings, and supersession chain are recoverable as they were at confirmation.

### AC-G02 [FE][J04] Empty and unavailable evidence is explicit

Given a line has no eligible stock, no timely incoming, no classification, or no location level,
when the side sheet renders, then each condition has an explicit empty or unavailable state and
relevant sections are not hidden.

### AC-G03 [FE][J05] Destructive or superseding action is confirmed

Given an authorized user attempts to discard a draft composition or supersede an active decision,
when the action is selected, then the shared confirmation dialog describes the affected SO and
line count; native `confirm()` is not used.

### AC-G04 [E2E][J01-J09] Human-readable navigation and error handling

Given the CS or buyer journey succeeds or fails, when the user follows it through normal menus,
then relevant screens use human-readable SO, item, project, and location identifiers, errors use
the shared API contract, and browser console and network checks show no unexpected failures.

### AC-G05 [BE][J09] Cancellation, keying, placement, and receipt count once

Given a Buy residual advances through keying, PO placement, partial receipt, cancellation, or SO
amendment, when the next run is built, then the ledger carries only the current unplaced balance
and no lifecycle event reintroduces or subtracts the same quantity twice.

### AC-G06 [BE][J01-J09] Read and write paths remain company-scoped

Given equivalent identifiers in two companies, when decisions, inquiry rows, plan rows, levels,
classifications, or drills are read or written, then only records belonging to the actor's company
participate and cross-company access is denied without leaking existence.

## Group H: Rollout and process gates

### AC-H01 [T][J01-J09] Baseline differences have regression tests

Given the implementation branch currently derives inquiry at publish, permits per-line partial
allocation, and requires accepted donor claims, when Stage 0 completes, then focused failing
contract tests capture each behavior before Stage 1C replaces it.

### AC-H02 [T][J01-J09] Stage order is enforced

Given this finalized UAC and plan, when implementation begins, then Stage 1A, 1B, 1C, 2, and 3
each follow Phase 1 frontend mock, Phase 2 backend TDD and implementation, and Phase 3 review; no
backend feature code precedes its approved frontend mock.

### AC-H03 [T][J01-J09] Every criterion is traced in the test report

Given implementation reaches its Definition of Done gate, when the test report is produced, then
every AC ID in this file has PASS, FAIL, or explicitly approved DEFERRED evidence from backend
pytest, frontend Vitest, or normal-navigation `agent-browser` verification as applicable.

### AC-H04 [T][J01-J09] Scope stays direct

Given any implementation slice, when its design is reviewed, then it introduces no LLM quantity
generation, new optimizer, generic rules engine, second Borrow approval, automatic supplier
ordering, reorder-level convergence worklist, or new configuration knob not required by this
contract.

## Definition of Done for the later implementation

- All AC IDs pass or have an explicitly approved deferral.
- Product and Location calculations reproduce from frozen inputs.
- Atomicity, idempotency, concurrency, permissions, and company isolation have backend tests.
- Both journeys pass normal-navigation browser verification with console and network review.
- Migrations, rollback behavior, and production-shaped reconciliation fixtures are reviewed.
- The UAC and plan remain aligned; any product change updates the UAC before implementation.
