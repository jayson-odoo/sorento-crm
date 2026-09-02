import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import {
  mockAugmentLocations,
  mockReorderLadderOptionsV8,
  POOLS_SET,
} from '../lib/fulfilmentV8Mock';
import type {
  AdoptSalesOrderResult,
  BoardCell,
  BoardContribution,
  BoardGranularity,
  ClassificationEvidence,
  PlanningBoard,
  ConfirmManyBody,
  ConfirmManyResult,
  ConfirmResult,
  ConfirmSupplyBody,
  FulfilmentPlanningListEnvelope,
  FulfilmentPlanningListParams,
  FulfilmentPlanningRow,
  PileQueue,
  ReconciliationSummary,
  StockDetail,
  SupplyFailingLine,
  SupplyProposal,
} from '../types/fulfilmentPlanning.types';

/**
 * Fulfilment Planning: the worklist of everything that needs planning, the reconciliation
 * behind one order, and the supply composition CS confirms on top of it.
 *
 * API CONTRACT. Source of truth is
 * `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` section 6, which
 * amends `STAGE1B-scm-front-planning-reconciliation.md` section 3 and
 * `STAGE1C-scm-front-planning-promising.md` section 6. A deviation updates that file and
 * both sides in the same change. Every route hangs off the existing `/api/v1/project-sales`
 * router, reads with `projects.projects.view`, writes with `projects.projects.edit`, and no
 * new permission is introduced.
 *
 *   GET  /project-sales/fulfilment-planning
 *        ?page&limit&query&review_state&project_id&sales_order_id
 *        -> { data: FulfilmentPlanningRow[], pagination: { total, page, limit } }
 *
 *        review_state is a CLOSED set, and the first value is the new one:
 *          not_started | awaiting_reconciliation | needs_cs_review | confirmed
 *        An unknown value is a 422, never an empty 200.
 *
 *        The list is a UNION of two arms, one row per subject, disjoint by construction:
 *          arm 1 `row_kind = 'sales_order'` - an outstanding project-class CORE sales
 *                order, whether or not anybody has planned it. Unplanned reads not_started
 *                and carries no `id`, no `provisional_ref` and no `status`, because no
 *                planning record exists to carry them.
 *          arm 2 `row_kind = 'planning_record'` - a Project SO authored here that has no
 *                core sales order yet (Stage 1B's Awaiting reconciliation).
 *        Ordered by `earliest_required_date` ascending, NULLS LAST, tie-broken on the
 *        sales-order number so the order is total and no row lands on two pages (AC-FP04).
 *        `query` matches sales-order number, customer name, the project string, project code
 *        and title, provisional ref, AutoCount doc no and area group.
 *
 *   POST /project-sales/fulfilment-planning/adopt
 *        body { sales_order_id }
 *        -> { project_sales_order_id, so_number, review_state, already_adopted }
 *        This is Start planning, and it is the whole of journey step 2: it writes one
 *        planning record plus one mirror line per open core line and asks nothing else. It
 *        is IDEMPOTENT (a second press, a retry or a second user answers with the record
 *        that exists and `already_adopted: true`), which is why it takes no confirmation
 *        dialog - it destroys nothing and it repeats safely.
 *        409 when another planning record already holds that core order, naming its
 *        reference; 404 when the sales order is out of the caller's company scope.
 *
 *   GET  /project-sales/sales-orders/{pso_id}/reconciliation -> ReconciliationSummary
 *   POST /project-sales/sales-orders/{pso_id}/reconcile      -> ReconciliationSummary
 *        Same route for both origins, dispatching on the record's status. For an ADOPTED
 *        order it is a one-way SYNC rather than a diff: `header.outcome` is `adopted` and
 *        its `reason` is the sentence the card shows, because there is no separately
 *        authored document to disagree with. Idempotent either way.
 *
 *   GET  /project-sales/sales-orders/{pso_id}/supply  -> SupplyProposal
 *        Additive to Stage 1C: `SupplyProposal.sales_order_number` (the human key),
 *        `SupplyProposal.sales_order_id` (addressing only, for the /scm link), nullable
 *        `project_id`, and per line `fulfilment_location_missing`.
 *
 *        THE FULFILMENT LOCATION IS THE CORE SALES-ORDER LINE'S OWN `warehouse_id`, per
 *        line (captain's decision, plan section 11 question 2). There is no endpoint to set
 *        it, no order-level "Fulfil from" question and no default: a line whose core line
 *        states no warehouse comes back with `fulfilment_location_missing: true`, no
 *        proposed component of any kind, and is refused by Confirm by name. It is fixed on
 *        the SCM sales order, which this screen links to.
 *
 *   POST /project-sales/sales-orders/{pso_id}/confirm -> ConfirmResult
 *        body ConfirmSupplyBody; 409/422 -> the shared AppException envelope plus the
 *        list: { message, detail, code, failing_lines: [{line_no, item_code, reason}] },
 *        nothing written (AC-C02)
 *
 * An exception's `message` carries the REASON only. The screen prints the subject itself
 * from `line_no` and `item_code` ("Line 2, SRT501-CP"), so a message that repeats it reads
 * as the same fact twice.
 *
 * The confirm POST is not a retry of a partial write: it either commits every line or
 * writes nothing at all.
 *
 * PHASE 2, and the mock is GONE. Seams A and B are live, so every function below is the
 * real call; there is no switch left to turn on and no fixture served from here. The Phase 1
 * fixtures survive only as test support, which is the whole of what "throwaway by design"
 * meant.
 *
 * ── S2 LADDER v8 (PLAN-scm-fulfilment-feedback-2sep.md, PHASE 1 - the overlay below, not
 *    the routes above) ─────────────────────────────────────────────────────────────────
 *
 * `getPlanningBoard`, `getSupply` and `getStockDetail` call `lib/fulfilmentV8Mock.ts` on
 * their own response, BEFORE returning it, to add three fields the v7.1 board/stock-detail
 * routes above do not send yet - the v8 engine change (this plan's S2) is Phase 2 for a
 * DIFFERENT slice, so this file fakes its wire shape rather than its numbers, over payloads
 * that are otherwise entirely real:
 *
 *   BoardCellLocation.available_for_project : string | null
 *     `cell.locations[]`, `contribution.locations[]` (board) - one per `site_pool` row and
 *     the "Site pool subtotal" row built from it (R-K). `0`, never blank, on an addressable
 *     pool row; absent on `own` / `group` / `other_group`.
 *
 *   StockDetail.five_pool_net : string | null
 *     `stock-detail` - only on a `group=pools` read, which is what the Stock tab's expanded
 *     ledger caps its running "Available for Project" column by, under a site-pool section
 *     (a plain bin or a non-pool group keeps "Balance after", uncapped, unchanged).
 *
 *   BoardLadderOption.step === 'pool_share', label "Use BRW stock", first in walk order
 *     `contribution.options[]` (board), `SupplyLine.options[]` (sheet) - today's `pool` step
 *     (last, before Buy) relabelled and moved first (R-A), carrying `gives_qty` (R-B).
 *
 * Phase 2 (S2's own Phase 2, not this slice's) deletes the `lib/fulfilmentV8Mock.ts` calls
 * the day `front_planning_engine.walk_line` and the board/stock-detail serializers send all
 * three for real; the functions below go back to `return response.json()` verbatim.
 */

const BASE = '/api/v1/project-sales';

/**
 * The repo's standard `{data, pagination: {...}}`, with the flat `{data, total, ...}` read
 * as a fallback for the same reason `projectSalesOrderService` reads it: a backend that
 * shipped against the earlier wording should degrade to a full grid, not a blank one.
 */
function normaliseEnvelope(
  body: unknown,
  fallbackLimit: number,
): FulfilmentPlanningListEnvelope {
  const raw = (body ?? {}) as {
    data?: FulfilmentPlanningRow[];
    total?: number;
    page?: number;
    limit?: number;
    pagination?: { total?: number; page?: number; limit?: number };
  };
  const rows = Array.isArray(raw.data) ? raw.data : [];
  return {
    data: rows,
    total: raw.pagination?.total ?? raw.total ?? rows.length,
    page: raw.pagination?.page ?? raw.page ?? 1,
    limit: raw.pagination?.limit ?? raw.limit ?? fallbackLimit,
  };
}

/**
 * Everything that needs planning, one row each: the outstanding core sales orders (planned
 * or not) and the Project SOs authored here that have no core order yet.
 */
export async function listFulfilmentPlanning(
  params: FulfilmentPlanningListParams = {},
): Promise<FulfilmentPlanningListEnvelope> {
  const limit = params.limit ?? 25;
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      // `sort` + `dir`, exactly as `buildDataGridParams` emits them. The sort is the SERVER's:
      // the grid never re-sorts the page it was handed, or the order on screen would disagree
      // with paging the moment there is more than one page.
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : undefined,
      searchQuery: params.query ?? '',
    },
    {
      review_state: params.review_state,
      project_id: params.project_id,
      sales_order_id: params.sales_order_id,
    },
  );
  const response = await apiFetch(`${BASE}/fulfilment-planning?${search.toString()}`);
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to load the fulfilment planning list'),
    );
  return normaliseEnvelope(await response.json(), limit);
}

/**
 * Start planning an outstanding core sales order (journey step 2).
 *
 * One decision, no form in between: the lines, products, quantities, required dates,
 * locations and customer are all derived from the order itself. Idempotent, so the button
 * is safe to press twice and safe for two people to press at once.
 */
export async function adoptSalesOrder(salesOrderId: string): Promise<AdoptSalesOrderResult> {
  const response = await apiFetch(`${BASE}/fulfilment-planning/adopt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sales_order_id: salesOrderId }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to start planning this sales order'));
  return response.json();
}

/** What reconciliation currently makes of one order. A pure read: it writes nothing. */
export async function getReconciliation(psoId: string): Promise<ReconciliationSummary> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/reconciliation`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the reconciliation'));
  return response.json();
}

/**
 * Re-run the mapping after CS has answered whatever was in the way (uploaded the AutoCount
 * document, answered a difference, or waited for the outstanding SO book to carry the
 * number). Idempotent, so the button is safe to press on an order that is already clean.
 */
export async function rerunReconciliation(psoId: string): Promise<ReconciliationSummary> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/reconcile`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to re-run the reconciliation'));
  return response.json();
}

/**
 * The composition the engine proposes for every line, its evidence, and the active
 * decision when one exists. A pure read: opening the sheet claims no stock.
 */
export async function getSupply(psoId: string): Promise<SupplyProposal> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/supply`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the supply composition'));
  const data: SupplyProposal = await response.json();
  // PHASE 1 MOCK (S2, `lib/fulfilmentV8Mock.ts`): v8's walk order, until the engine sends it.
  return {
    ...data,
    lines: data.lines.map((line) => ({
      ...line,
      options: mockReorderLadderOptionsV8(line.options),
    })),
  };
}

/**
 * A refused confirmation, carrying the lines that refused it.
 *
 * `extractApiError` answers with a string, and the 422 body's `failing_lines` is a list the
 * sheet prints line by line, so the message alone would lose exactly the part CS acts on.
 * Same shape of problem as the prompt registry's validation body.
 */
export class ConfirmSupplyError extends Error {
  readonly failingLines: SupplyFailingLine[];

  constructor(message: string, failingLines: SupplyFailingLine[] = []) {
    super(message);
    this.name = 'ConfirmSupplyError';
    this.failingLines = failingLines;
  }
}

/**
 * Confirm the whole sales order once (AC-C01). Every line commits together or none does,
 * so there is no per-line call and no partial state to resume from.
 */
export async function confirmSupply(
  psoId: string,
  body: ConfirmSupplyBody,
): Promise<ConfirmResult> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    // The message goes through the shared extractor like everywhere else; the clone is
    // what carries the failing lines, because a body can only be read once and the
    // extractor answers with a string.
    const clone = response.clone();
    const message = await extractApiError(response, 'Failed to confirm this sales order');
    let failingLines: SupplyFailingLine[] = [];
    try {
      const payload = (await clone.json()) as { failing_lines?: SupplyFailingLine[] };
      if (Array.isArray(payload?.failing_lines)) failingLines = payload.failing_lines;
    } catch {
      // Not JSON, so there are no failing lines to name and the message is the answer.
    }
    throw new ConfirmSupplyError(message, failingLines);
  }
  return response.json();
}

/**
 * The multi-order planning board (PLAN section 13).
 *
 * CONTRACT:
 *
 *   GET /project-sales/fulfilment-planning/board
 *       ?orders=SO391698,SO324265,...        // sales-order NUMBERS, never ids (13.2)
 *       &granularity=week|month              // default week; exact dates are never columns
 *       -> PlanningBoard
 *
 *       Read-only. Opening the board claims no stock and writes nothing, exactly as opening
 *       the per-order sheet does not.
 *
 *       `as_of` is the date the server built it against, echoed back so "overdue" is
 *       reproducible rather than whatever the client's clock said.
 *
 *       Cells are returned only for (product, bucket) pairs somebody owes. A pair with no
 *       cell renders blank, and a blank cell is NOT a zero: it means no selected order owes
 *       that product by that date.
 *
 *       Allocation across competing lines is the server's, computed per (product, location)
 *       in the 13.5 order (earliest required date, then stated priority, then sales-order
 *       number), and every contribution carries `contested` when an earlier line actually
 *       took the free stock it would otherwise have had.
 *
 * THERE IS NO BOARD WRITE ENDPOINT, and that is the design (13.4). The board is a LENS: the
 * decision stays per sales order and atomic across its lines, so approve / amend / reject are
 * held in a client draft and the commit is the EXISTING per-order confirm:
 *
 *   POST /project-sales/sales-orders/{pso_id}/confirm   // one call per order, unchanged
 *
 * Committing a selection is therefore N independent atomic confirmations, not one
 * transaction. A refusal reports per order and the orders that committed stay committed
 * (13.6).
 *
 * ── LADDER v7.1: THE OPTIONS CONTRACT (S3, R36, AC-S3-14) ───────────────────────────────
 *
 * Additive to the payload above. Every contribution the ladder WALKED (so: not unplannable,
 * not covered by a frozen decision) carries, alongside its `trail`:
 *
 *     options: [{
 *       step:           'use' | 'order_borrow' | 'supply_borrow' | 'pool' | 'buy',
 *       label:          string,           // the step in a planner's words, the SERVER's sentence
 *       whole:          boolean,          // does it cover the WHOLE planning unit (R10, R33)
 *       fulfil_date:    'YYYY-MM-DD'|null,// when the unit would be fulfilled if it were taken
 *       days_late:      number|null,      // days after the line's required date; 0 = on time
 *       debt_so_number: string|null,      // whose order pays for it, by DOCUMENT NUMBER
 *       debt_month:     'YYYY-MM'|null,   // the month that debt lands in on the Stock Debt view
 *       chosen:         boolean           // the option the engine proposed
 *     }]
 *
 * FIVE ENTRIES, ALWAYS, IN STEP ORDER - `use`, `order_borrow`, `supply_borrow`, `pool`, `buy` -
 * and every one of them answered, for the same reason the trail sends five rows: a step the
 * server omitted reads as a step nobody walked. The client renders them in the order they
 * arrive and never sorts them.
 *
 * `fulfil_date` is today for on hand (plus two days when a transfer between bins is needed),
 * the SPO's arrival, the PO's `issue + lead` (R29: a PO line's `expected_date` is what it was
 * BOUGHT FOR, never an arrival), and `as_of + lead` for Buy. It is null exactly when the step
 * gives nothing, and `days_late` is null with it: "nothing was offered" and "offered, on time"
 * are different answers and the table shows them differently.
 *
 * `days_late` is never negative. Landing before the required date is on time, not "minus six
 * days late", and the screen renders 0 as blank.
 *
 * `debt_so_number` / `debt_month` are set on the two borrow steps only. `use` draws the FREE
 * pile and `buy` orders new stock, so neither owes anybody and both send null rather than an
 * empty string.
 *
 * At most ONE option carries `chosen: true` - the first whole one in step order, which is the
 * composition `sources` states. None carries it when nothing covers the unit.
 *
 * The trail's five questions arrive in the same order and are worded (AC-S3-11):
 * `Can we use our locations?`, `Can we borrow on hand from a later order?`, `Can we borrow
 * incoming from a later order?`, `Can we take from the pool?`, `Buy`. The on-hand borrow's
 * `why` names what is borrowed, from whom, when they are due and where the debt lands:
 * `Borrow 30 on hand at MWH-IB from SO414285 line 4 (JEREMY, due 12 Nov 2026); its debt lands
 * in Nov 2026`.
 *
 * ── LADDER v7.1 STEP 3: BORROW INCOMING (S4, R27/R32/R33/R35) ──────────────────────────
 *
 * A step-3 source is kind `borrow` with `rung: 'supply_borrow'`, and it carries three fields
 * no other rung sends:
 *
 *     supply_key:      'spo:<allocation id>' | 'po:<purchase order line id>'   // ADDRESSING ONLY
 *     supply_document: 'SPO 202607-S0105' | 'PO 202607-P0031 line 3'           // what a person reads
 *     arrival_date:    'YYYY-MM-DD'                                            // when it lands
 *
 * `supply_key` is never rendered: it is the address the Confirm moves the placement link onto
 * (`order_inquiry_links.spo_allocation_id | po_line_id`), and it is keyed by ID rather than by
 * document number because a re-import changes the number and not the row. `supply_document` is
 * the SERVER's spelling of the same document; the client prints it and never assembles it.
 * All three round-trip through `ConfirmBorrowComponent` verbatim - a proposal approved as it
 * stands has to move the placement the ENGINE named, and a Confirm that arrives without them
 * is re-checked against free stock at a bin holding a container that has not landed.
 *
 * ONE DOCUMENT COVERS THE WHOLE UNIT OR THE STEP GIVES NOTHING (R33), so every step-3 source
 * on a line names the SAME document; several of them mean several holders of it (its free
 * share first, then each donor). A source with no `donor_so_number` is the FREE share: nobody
 * was waiting on it, so it raises no order-back and its sentence reads "Take" rather than
 * "Borrow".
 *
 * `BoardBorrowCandidate` (the manual `BorrowAddDialog`'s list) reads the SAME donors as step 2
 * and in the same order, which the server sets and the dialog never re-sorts:
 * `(same_agent desc, required_date desc, same_group desc, same_warehouse desc)` (R4, R19) -
 * her own agent first, then the latest-dated order (it can wait longest), then the same
 * ownership group, then the asker's own warehouse (fewest transfers). Phase 2 wires that
 * ordering; the dialog needs no change for it.
 *
 * PHASE 2 (S3), and the mock is GONE. `propose_line` returns the five options for real and
 * this function reads them straight off the payload; `lib/ladderOptionsMock.ts` and the
 * `NEXT_PUBLIC_LADDER_OPTIONS_MOCK` flag it hung off are deleted, so the flag being set on a
 * running dev server does nothing at all.
 */
export async function getPlanningBoard(
  soNumbers: string[],
  granularity: BoardGranularity = 'week',
  /**
   * Rank by a what-if policy instead of the live one (13.5, recommendation 3). Read-only: a
   * previewed ranking is labelled on screen and may never be committed against.
   *
   * `true` asks for the server's default preview; a STRING asks for a policy by name, which is
   * what lets a second what-if exist without another boolean.
   */
  previewPolicy: boolean | string = false,
  options: {
    /** First day of the day-granularity window. Only meaningful at day granularity. */
    dayWindow?: string;
    /** Pin the board to a date, so "overdue" is reproducible in an evidence run. */
    asOf?: string;
  } = {},
): Promise<PlanningBoard> {
  const search = new URLSearchParams({ orders: soNumbers.join(','), granularity });
  // Omitted rather than sent empty: the route reads presence, and `preview_policy=` would be
  // an unknown policy NAME rather than "no preview" (404, per the route's contract).
  if (previewPolicy) {
    search.set('preview_policy', previewPolicy === true ? '1' : previewPolicy);
  }
  if (options.dayWindow) search.set('day_window', options.dayWindow);
  if (options.asOf) search.set('as_of', options.asOf);
  const response = await apiFetch(`${BASE}/fulfilment-planning/board?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the planning board'));
  const data: PlanningBoard = await response.json();
  return mockAugmentBoard(data);
}

/**
 * PHASE 1 MOCK (S2, `lib/fulfilmentV8Mock.ts`): `available_for_project` on every site-pool
 * location row and v8's ladder-option order, applied to BOTH homes a contribution's numbers
 * live in - a cell's own `contributions` (windowed) and the board's flat, never-windowed
 * `contributions` (`PlanningBoard.contributions` - "Approve all" and the List view read this
 * one, not the cells). The two are separate arrays over the wire, so augmenting only one
 * would leave the other reading v7.1's numbers depending which surface asked.
 *
 * Every array is read defensively (`?? []`, `?.map`): a minimal fixture built only to assert
 * the URL a call makes (`{ cells: [] }`, no top-level `contributions`) is not this function's
 * business to reject, and the real route always sends both.
 */
function mockAugmentBoard(board: PlanningBoard): PlanningBoard {
  return {
    ...board,
    cells: (board.cells ?? []).map(
      (cell): BoardCell => ({
        ...cell,
        locations: mockAugmentLocations(cell.locations),
        contributions: (cell.contributions ?? []).map(mockAugmentContribution),
      }),
    ),
    contributions: (board.contributions ?? []).map(mockAugmentContribution),
  };
}

function mockAugmentContribution(contribution: BoardContribution): BoardContribution {
  return {
    ...contribution,
    locations: mockAugmentLocations(contribution.locations),
    options: mockReorderLadderOptionsV8(contribution.options),
  };
}


/**
 * What a location row of the cell's stock table is made of (AutoCount's "Stock Status with
 * Detail"), expanded under that row - or what a whole ownership GROUP is made of, under its
 * subtotal row.
 *
 * Addressed by IDS, never by item code: two products on the live book share the code
 * `B2155-NL-BLUE`, so a lookup by code would answer confidently about the wrong one.
 */
export async function getStockDetail(
  productId: string,
  warehouseId: string | null,
  lineIds: string[] = [],
  /**
   * A whole SET instead of one bin: the ownership-group suffix (`IB`), or `pools` for the
   * five site pools. Step 1 of the ladder draws the group's pile - a `BRW-IB` line is fed by
   * `MWH-IB` stock - so a running balance is only true when it is read over the group.
   */
  group?: string | null,
): Promise<StockDetail> {
  const search = new URLSearchParams({ product_id: productId });
  if (group) search.set('group', group);
  else if (warehouseId) search.set('warehouse_id', warehouseId);
  // The lines the drawer is planning. Their rows come back marked `is_this_line`; an absent
  // parameter reads the list on nobody's behalf.
  if (lineIds.length > 0) search.set('line_ids', lineIds.join(','));
  const response = await apiFetch(
    `${BASE}/fulfilment-planning/stock-detail?${search.toString()}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the stock detail'));
  const data: StockDetail = await response.json();
  // PHASE 1 MOCK (S2, `lib/fulfilmentV8Mock.ts`): a `group: 'pools'` read's own `available_qty`
  // already IS the five-pool net (both read `netting().pools_net()`); Phase 2 exposes it under
  // its own name instead of this alias.
  return {
    ...data,
    five_pool_net: data.group === POOLS_SET ? data.available_qty : (data.five_pool_net ?? null),
  };
}

/**
 * The whole queue at one pile, in the order the stock is served.
 *
 *   GET /project-sales/fulfilment-planning/queue?product_id=&warehouse_id=&line_id=
 *
 * The captain, after being shown the top three beside a rung: "I need to know what is ahead of
 * me to have the visibility, and why they are ahead of me, meaning I need to know their rank
 * also."
 *
 * `lineId` is the CORE sales-order line asking. It marks its own row, states its position, and
 * makes every row above it say WHICH factor put it there. Omitted reads the queue on nobody's
 * behalf, which is what the pile looks like to somebody who is not in it.
 */
export async function getPileQueue(
  productId: string,
  warehouseId: string,
  lineId?: string | null,
): Promise<PileQueue> {
  const search = new URLSearchParams({ product_id: productId, warehouse_id: warehouseId });
  if (lineId) search.set('line_id', lineId);
  const response = await apiFetch(`${BASE}/fulfilment-planning/queue?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the queue'));
  return response.json();
}

/**
 * The Proof button: the ranked evidence behind one product's hot/cold verdict.
 *
 *   GET /project-sales/fulfilment-planning/classification?product_id=
 *
 * The captain, reading the trail: "don't give me jargon like abc classification, just tell
 * me hot selling or cold selling, at project or retail, with some button for me to view
 * detail as a proof". This is that button's data.
 */
export async function getClassificationEvidence(
  productId: string,
): Promise<ClassificationEvidence> {
  const search = new URLSearchParams({ product_id: productId });
  const response = await apiFetch(
    `${BASE}/fulfilment-planning/classification?${search.toString()}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the evidence'));
  return response.json();
}

/**
 * "Confirm all approved" (D3): every order's Confirm, in ONE call.
 *
 *   POST /project-sales/fulfilment-planning/confirm-all
 *        body { orders: [{ pso_id, lines: ConfirmLine[] }] }
 *        -> { results: [{ pso_id, ok, decision_revision?, inquiry_rows_created?,
 *                          lines_decided?, lines_undecided?, error?, failing_lines? }] }
 *
 * Each order commits or refuses on its OWN: one order's stale line does not take the
 * orders around it down, and every order named in the body gets a result either way - the
 * caller never has to guess whether a missing entry means it committed or was skipped.
 * `extractApiError` is not enough here: a 200 can still carry `ok: false` entries, so the
 * caller reads `results` even on a successful response.
 */
export async function confirmMany(body: ConfirmManyBody): Promise<ConfirmManyResult> {
  const response = await apiFetch(`${BASE}/fulfilment-planning/confirm-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to confirm the approved decisions'),
    );
  return response.json();
}
