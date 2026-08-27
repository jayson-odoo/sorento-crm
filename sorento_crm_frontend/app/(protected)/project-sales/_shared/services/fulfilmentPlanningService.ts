import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  AdoptSalesOrderResult,
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
  return response.json();
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
  return response.json();
}


/**
 * What a location row of the cell's stock table is made of (AutoCount's "Stock Status with
 * Detail"), expanded under that row.
 *
 * Addressed by IDS, never by item code: two products on the live book share the code
 * `B2155-NL-BLUE`, so a lookup by code would answer confidently about the wrong one.
 */
export async function getStockDetail(
  productId: string,
  warehouseId: string,
  lineIds: string[] = [],
): Promise<StockDetail> {
  const search = new URLSearchParams({ product_id: productId, warehouse_id: warehouseId });
  // The lines the drawer is planning. Their rows come back marked `is_this_line`; an absent
  // parameter reads the list on nobody's behalf.
  if (lineIds.length > 0) search.set('line_ids', lineIds.join(','));
  const response = await apiFetch(
    `${BASE}/fulfilment-planning/stock-detail?${search.toString()}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the stock detail'));
  return response.json();
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
