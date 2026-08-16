# UAC: SCM Front Planning

**Status:** FINALIZED, grilled and pre-code, 16 August 2026

**Plan:** `documentation/plans/scm/PLAN-scm-front-planning.md`

**Scope:** Project Fulfilment Planning through the Product and Location SCM plan views.

These criteria are the binding contract. Each criterion is independently verifiable. Terms and
formulas have the meanings defined in the linked plan.

## Guided journey

Customer Service starts with an accepted Project PO and schedule, releases an AutoCount SO,
reconciles its lines, reviews an evidence-backed Reserve / Borrow / Buy composition, and confirms
the entire Project SO once. Purchasing then receives only confirmed Buy residuals and can work
one frozen SCM run at Product or Location grain without duplicating the purchase decision.

The successful journey ends when every SO line has named, balanced supply; Order Inquiry contains
only unplaced Buy; Product and Location views explain the same run; and the chosen purchase total
is linked into the existing keying and fulfilment ledger.

## Group A: Release and reconciliation

### AC-A01 [E2E] Accepted demand reaches one review journey

Given an accepted Project PO version and delivery schedule, when CS creates the release proposal,
exports the AutoCount worksheet, uploads the resulting SO, and follows normal application
navigation, then the Project SO is reconciled and opens in Project Fulfilment Planning without
creating purchasing demand before confirmation.

### AC-A02 [BE] Header and line reconciliation is mandatory

Given a Project SO, when reconciliation completes, then its core SO header is linked and each
Project SO line has exactly one core SO-line link; a missing, duplicate, or ambiguous link prevents
the SO from becoming confirmable and returns a human-readable line number and item code.

### AC-A03 [FE] The whole SO has one pre-confirmation state

Given a reconciled but unconfirmed Project SO, when any user views its header, list row, or side
sheet, then the whole SO reads **Needs CS review** and no line is labeled partially confirmed,
confirmed, or purchasing-ready.

### AC-A04 [BE] Pre-confirmation demand is excluded

Given any Project SO in **Needs CS review**, when Order Inquiry and SCM demand readers run, then
all lines from that SO contribute zero purchase requirement.

## Group B: Deterministic coverage and suggestions

### AC-B01 [BE] The line balance uses current open quantity

Given a reconciled Project SO line, when its suggestion is calculated, then the starting quantity
is the core SO line's current open fulfilment quantity in the line UOM, not the original customer
quantity and not a value reduced again by a downstream reader.

### AC-B02 [BE] Only timely line-allocated SPO covers demand

Given inbound SPO quantities, when coverage is calculated, then only quantity already allocated
to the exact core SO line and expected on or before that line's required date contributes timely
allocated incoming.

### AC-B03 [FE] Unallocated and late incoming is advisory

Given matching inbound that is unallocated or arrives after the required date, when CS opens the
side sheet, then it is labeled advisory, contributes zero to the balance, and cannot be selected
as coverage from that sheet.

### AC-B04 [BE] Suggestions are deterministic

Given identical frozen stock, claims, incoming, classification, reorder level, dates, and SO data,
when the suggestion is calculated twice, then timely incoming, Reserve, Borrow candidates, and
Buy are identical and no LLM or nondeterministic optimizer supplies a quantity.

### AC-B05 [BE] Hot-selling uses existing ABC facts

Given a product, when Reserve eligibility is calculated, then it is dealer hot-selling exactly
when a current `scm.item_classification` row has ABC A at an active, available warehouse whose
stored `segment` is `dealer`; `computed_at` is evidence rather than a freshness gate, and when no
classification row exists for any qualifying warehouse the sheet shows **Retail classification
unavailable** rather than inferring a class.

### AC-B06 [BE] Hot-selling Reserve protects dealer and BRW stock

Given a dealer hot-selling product, when Reserve is proposed, then dealer-facing free stock
contributes zero and the maximum BRW Reserve is
`max(BRW free unclaimed stock - coalesce(BRW per-location reorder level, 0), 0)`.

### AC-B07 [BE] Non-hot-selling Reserve stays inside its boundary

Given a product that is not dealer hot-selling, when Reserve is proposed, then only free
unclaimed stock in the SO's own fulfilment location or shared BRW contributes; stock elsewhere
or committed to another SO is presented as Borrow, not Reserve.

### AC-B08 [T] The hot-selling worked case is fixed

Given a hot-selling product with need 70, dealer-facing free stock 50, BRW free unclaimed stock
120, and BRW reorder level 80, when the proposal is calculated, then Reserve is 40, dealer-facing
Reserve is 0, and the Borrow-or-Buy residual is 30.

### AC-B09 [FE] Borrow evidence and reason are mandatory

Given CS selects Borrow, when the side sheet validates the line, then it shows the donor location
or SO/project, quantity, current donor shortfall or days-of-cover impact, and a required reason;
the Confirm action remains disabled until a reason is entered.

### AC-B10 [BE] Borrow has no second approver

Given a valid Borrow selection and reason, when the authorized CS actor confirms the Project SO,
then that confirmation is sufficient to commit Borrow and no intermediate request, donor-CS
acceptance action, or second approver is required; cross-project Borrow may write its audit claim
directly in the terminal accepted state in the same transaction.

### AC-B11 [E2E] Discontinued Buy is allowed with control

Given committed customer demand for a discontinued product and a positive Buy residual, when CS
reviews the line, then a visible warning and required reason are shown; after the reason is
entered, the SO may be confirmed and the Buy residual reaches Purchasing without automatic
substitution.

### AC-B12 [BE] Every proposal balances

Given a proposed line, when the engine returns it, then all quantities are non-negative and
`open quantity = timely allocated incoming + Reserve + Borrow + Buy`; otherwise the line is an
explicit calculation error and cannot be confirmed.

### AC-B13 [BE][T] Confirmed cover is unavailable to later demand

Given Reserve or Borrow is confirmed for one SO, when a later CS proposal or Retail replenishment
calculation reads the same product and source, then the confirmed quantity reduces free supply in
both calculations and cannot be proposed or consumed a second time.

## Group C: Atomic Project SO confirmation

### AC-C01 [E2E] One action confirms all lines

Given a Project SO with multiple valid balanced lines, when authorized CS presses **Confirm
Project SO** once, then every line becomes committed in one transaction and the SO leaves
**Needs CS review**; there is no per-line confirmation action or durable partial state.

### AC-C02 [BE] One invalid line rolls back the SO

Given one line becomes stale, over-allocated, unbalanced, unmapped, or invalid while other lines
remain valid, when confirmation is attempted, then no decision, allocation, claim, or inquiry row
from that attempt is committed and every failing line is returned by line number and item code.

### AC-C03 [BE] Confirmation rechecks authoritative facts

Given a side sheet was opened earlier, when confirmation begins, then the service re-reads open
quantity, line mapping, incoming allocations and dates, free unclaimed stock, claims, ABC facts,
reorder levels, donor impact, and product lifecycle before writing.

### AC-C04 [BE] One active revision represents the SO

Given a confirmed Project SO, when its decision is read, then exactly one active SO-level revision
contains one snapshot for every SO line and each snapshot records all balance components and
evidence identifiers.

### AC-C05 [BE] Concurrent confirmations cannot double-claim

Given two actors attempt to confirm competing uses of the same stock or incoming allocation,
when the transactions race, then at most one commits the disputed quantity and the other returns
a refresh-required conflict without partial writes.

### AC-C06 [E2E] Material change reopens the whole SO

Given a confirmed Project SO, when quantity, required date, product mapping, core line link, or a
material supply fact changes, then the active revision is superseded or challenged, the whole SO
returns to **Needs CS review**, and no line remains independently confirmed.

### AC-C07 [BE] Existing execution is preserved on reconfirmation

Given a prior Buy has been placed or received, when a later revision lowers or removes need, then
placed or received supply remains in the ledger and an actionable exception is created rather
than deleting history or making the quantity available to buy again.

### AC-C08 [BE] Authorization and company isolation apply to the transaction

Given an actor lacks the required CS permission or belongs to another company, when confirmation
is attempted, then it is denied and no cross-company SO, stock, incoming, decision, or inquiry
fact is disclosed or changed.

## Group D: Buy-only Order Inquiry

### AC-D01 [BE] Inquiry is created only at successful confirmation

Given a Project SO is published or reconciled but not confirmed, when its lifecycle advances,
then no standard Order Inquiry demand row is created; when atomic confirmation commits, inquiry
rows are created or refreshed in that same transaction.

### AC-D02 [BE] Inquiry quantity equals confirmed Buy

Given a confirmed decision line, when `buy_qty > 0`, then exactly one active unplaced inquiry row
exists with that quantity; when `buy_qty = 0`, no active purchase row exists for the line.

### AC-D03 [T] Coverage never enters purchasing demand

Given any amounts of timely allocated incoming, Reserve, Borrow, late incoming, or unallocated
incoming, when Order Inquiry and SCM readers run, then those amounts contribute zero demand and
only the confirmed Buy residual is counted.

### AC-D04 [BE] Inquiry does not net supply again

Given a confirmed Buy row, when it is read into SCM, then the reader uses its current unplaced
quantity directly and does not repeat pre-order, inbound, stock, or customer-delivery netting.

### AC-D05 [BE] Handoff is idempotent across retries and revisions

Given confirmation is retried or a decision is superseded, when inquiry rows are refreshed, then
there is at most one active unplaced row for the active decision line, the old row remains
auditable, and placed or received quantities are not duplicated.

### AC-D06 [FE] Purchasing can trace Buy to its decision

Given a buyer expands a Project contribution, when the inquiry row is shown, then the UI links it
to the human-readable Project SO, line number, item code, required date, and decision revision,
without displaying a UUID.

## Group E: Deterministic channels and Product grain

### AC-E01 [BE] Channel derives from the SO market segment

Given an SO market segment, when demand class is assigned, then canonical project or spike
segments map to Project, dealer/retail/end-user segments map to Retail, and no AI, salesperson,
warehouse, or free-text inference participates.

### AC-E02 [BE] Unmapped channel is explicit

Given an absent or unmapped market segment, when classification runs, then demand remains
Unclassified, is excluded from Project and Retail labeled totals, and blocks Project SO
confirmation or appears as a buyer-plan data-quality exception for other SOs.

### AC-E03 [FE] Product grain is one row with stacked readings

Given a frozen SCM run containing multiple locations and channels for one product, when **Plan
grain: Product** is selected, then one company-wide product row shows separate Project, Retail,
and Unclassified readings plus total raw requirement, supplier rounding, suggested quantity,
chosen quantity, supplier, cash impact, and lifecycle state.

### AC-E04 [BE] Project demand is confirmed unplaced Buy

Given Project SO decisions in mixed lifecycle states, when Product grain is built, then Project
quantity is the sum of current confirmed Buy not yet placed, cancelled, or otherwise discharged,
and unconfirmed, Reserve, Borrow, covered incoming, and already placed quantity are excluded.

### AC-E05 [BE] Firm Project Buy bypasses reorder suppression

Given positive confirmed unplaced Project Buy and Retail demand below its reorder trigger, when
the product row is calculated, then Project Buy remains in raw product requirement and cannot be
suppressed by the Retail reorder level.

### AC-E06 [BE] Supplier constraints are applied once

Given raw Project plus Retail requirement for a product, when Product suggested quantity is
calculated, then MOQ and order multiple are applied once after aggregation, not once per SO line
or location.

### AC-E07 [FE] Product evidence is drillable

Given a product row, when Project or Retail is expanded, then the buyer can trace Project to SO
lines and decision/inquiry revisions and Retail to location stock, velocity, incoming, reorder,
and allocation evidence.

## Group F: Dual plan grains and reconciliation

### AC-F01 [FE] Both selectors remain distinct

Given the buyer plan, when its controls render, then it offers **Plan grain: Product / Location**
and separately offers **Planning mode: Auto / Manual**; choosing either control does not rename,
hide, or mutate the other vocabulary.

### AC-F02 [E2E] Location grain remains selectable

Given a frozen run with `decision_grain = location`, when **Plan grain: Location** is selected,
then existing per-location Buy recommendations, decisions, overrides, net positions, reorder
levels, and allocation evidence remain actionable; Product grain has not retired or replaced
them.

### AC-F03 [BE] Both grains share one frozen input set

Given Product and Location views for a run, when their evidence is inspected, then both use the
same company, as-of time, demand, stock, incoming, policy, supplier facts, and source revision.

### AC-F04 [BE] Product reorder level is a sum

Given per-location reorder levels for a product, when Product grain is calculated, then Product
reorder level equals `sum(coalesce(location level, 0))`; absent location rows and NULL values
contribute 0, and a product-wide NULL-warehouse row is not chosen as a competing winner.

### AC-F05 [BE] Location mode keeps location levels

Given the same product, when Location grain is calculated, then each row reads its own
per-location reorder level with NULL treated as 0 for this feature; no product-level sum is
written back over those rows.

### AC-F06 [FE] There is no level worklist state

Given absent or NULL location levels, when either grain renders, then no inferred winner,
**Needs level** state, or buyer level-convergence worklist is introduced by this feature.

### AC-F07 [BE] Reconciliation bridge reproduces the difference

Given Product suggested quantity and the sum of Location suggestions differ, when the bridge is
calculated, then the difference is fully reproduced by the displayed cross-location netting
delta and round-each versus round-once delta from the same frozen inputs; an unexplained non-zero
difference is a blocking calculation error.

### AC-F08 [FE] Reconciliation is visible before action

Given either plan grain, when a buyer opens a product, then the UI shows summed location reorder
level, product raw need, sum of location raw needs, both suggested totals, both reconciliation
deltas, and the chosen quantity's allocation back to locations.

### AC-F09 [BE] Exactly one grain is actionable per run

Given a run has no saved decisions, when the buyer first saves in Product or Location grain, then
that grain is locked as `decision_grain`; Product uses `order_summary_row` decisions, Location
uses existing recommendation decisions and overrides, and PO worklists ignore the other grain.

### AC-F10 [E2E] A decided run cannot change actionable grain

Given the first Product or Location decision has been saved, when a buyer tries to make the other
grain actionable for that frozen run, then the change is rejected and all existing decisions and
overrides remain immutable; the buyer must create a new current run with a new frozen snapshot,
and no second purchasing action is created from the old run.

### AC-F11 [T] Round-once behavior is demonstrable

Given two locations each have raw need 1 and the supplier multiple is 10 with no other netting,
when the run is calculated, then Location suggestions sum to 20, Product suggestion is 10 after
rounding aggregate need 2, and the bridge identifies 10 as the round-each versus round-once
difference.

### AC-F12 [T] Cross-location netting behavior is demonstrable

Given one location is short 10, another has 4 transferable surplus, no MOQ changes the result,
and all facts share one run, when both grains are calculated, then Location raw need sum is 10,
Product raw need is 6, Product suggestion is 6, and the bridge identifies 4 as cross-location
netting rather than an unexplained mismatch.

## Group G: Audit, lifecycle, and usability

### AC-G01 [BE] Decision evidence is immutable and attributable

Given a confirmed decision, when it is audited later, then the actor, timestamp, SO revision,
line quantities, incoming references, stock sources, ABC and reorder evidence, donor impact,
reasons, warnings, and supersession chain are recoverable as they were at confirmation.

### AC-G02 [FE] Empty and unavailable evidence is explicit

Given a line has no eligible stock, no timely incoming, no classification, or no location level,
when the side sheet renders, then each condition has an explicit empty or unavailable state and
relevant sections are not hidden.

### AC-G03 [FE] Destructive or superseding action is confirmed

Given an authorized user attempts to discard a draft composition or supersede an active decision,
when the action is selected, then the shared confirmation dialog describes the affected SO and
line count; native `confirm()` is not used.

### AC-G04 [E2E] Human-readable navigation and error handling

Given the CS or buyer journey succeeds or fails, when the user follows it through normal menus,
then relevant screens use human-readable SO, item, project, and location identifiers, errors use
the shared API contract, and browser console and network checks show no unexpected failures.

### AC-G05 [BE] Cancellation, keying, placement, and receipt count once

Given a Buy residual advances through keying, PO placement, partial receipt, cancellation, or SO
amendment, when the next run is built, then the ledger carries only the current unplaced balance
and no lifecycle event reintroduces or subtracts the same quantity twice.

### AC-G06 [BE] Read and write paths remain company-scoped

Given equivalent identifiers in two companies, when decisions, inquiry rows, plan rows, levels,
classifications, or drills are read or written, then only records belonging to the actor's company
participate and cross-company access is denied without leaking existence.

## Group H: Rollout and process gates

### AC-H01 [T] Baseline differences have regression tests

Given the implementation branch currently derives inquiry at publish, permits per-line partial
allocation, and requires accepted donor claims, when Stage 0 completes, then focused failing
contract tests capture each behavior before Stage 1C replaces it.

### AC-H02 [T] Stage order is enforced

Given this finalized UAC and plan, when implementation begins, then Stage 1A, 1B, 1C, 2, and 3
each follow Phase 1 frontend mock, Phase 2 backend TDD and implementation, and Phase 3 review; no
backend feature code precedes its approved frontend mock.

### AC-H03 [T] Every criterion is traced in the test report

Given implementation reaches its Definition of Done gate, when the test report is produced, then
every AC ID in this file has PASS, FAIL, or explicitly approved DEFERRED evidence from backend
pytest, frontend Vitest, or normal-navigation `agent-browser` verification as applicable.

### AC-H04 [T] Scope stays direct

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
