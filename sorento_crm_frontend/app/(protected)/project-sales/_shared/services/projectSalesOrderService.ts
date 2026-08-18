import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import { filenameFromContentDisposition } from './fileDownload';
import type {
  AmendmentCreateBody,
  AmendmentCreated,
  AmendmentDetail,
  AmendmentPreview,
  AmendmentPreviewBody,
  PoVersionOption,
  ProjectSalesOrderDetail,
  ProjectSalesOrderListParams,
  ProjectSalesOrderRow,
  SalesOrderBulkDeleteResult,
  SalesOrderDeleteResult,
  SalesOrderDocumentSaveBody,
  SalesOrderLineUpdateBody,
  SalesOrderPublishBody,
  SalesOrderPublishResult,
  SalesOrderRegroupGroup,
  SalesOrderSplitBy,
  SalesOrderWorksheet,
  ScheduleVersionOption,
} from '../types/projectSalesOrder.types';

const BASE = '/api/v1/project-sales';

/**
 * Sales order drafts, their findings and their amendments (contract sections 5 and 6).
 *
 * `NEXT_PUBLIC_PROJECT_SO_MOCK=1` serves the fixtures at the bottom of this file instead of
 * calling the API, which is how the review states (blocked, acknowledged, date-only delta,
 * unmatched) are reachable while the backend for the same contract is still being written.
 * Unset, every function is the real call.
 */
export const PROJECT_SO_MOCK = process.env.NEXT_PUBLIC_PROJECT_SO_MOCK === '1';

export interface SalesOrderListEnvelope {
  data: ProjectSalesOrderRow[];
  total: number;
  page: number;
  limit: number;
}

/**
 * List responses are the repo's standard `{data, pagination: {total, page, limit}, empty}`.
 * The contract originally said `{data, total, page, limit}` and integration corrected it on
 * 2026-08-02; the flat shape is still read as a fallback so a backend that shipped against
 * the earlier wording does not blank the grid.
 */
function normaliseEnvelope(
  body: unknown,
  fallbackLimit: number,
): SalesOrderListEnvelope {
  const raw = (body ?? {}) as {
    data?: ProjectSalesOrderRow[];
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

// ------------------------------------------------------------------ P7: drafts

/**
 * Builds (or rebuilds) the drafts for one PO version plus schedule version pair.
 *
 * `splitBy` picks the key the drafted lines are cut on. It defaults to `area` so every
 * existing caller keeps the schedule-area split it had.
 */
export async function buildSalesOrders(
  poId: string,
  scheduleVersionId: string,
  splitBy: SalesOrderSplitBy = 'area',
): Promise<SalesOrderListEnvelope> {
  if (PROJECT_SO_MOCK) return mockList();
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/build-sales-orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schedule_version_id: scheduleVersionId, split_by: splitBy }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to build the sales order drafts'));
  return normaliseEnvelope(await response.json(), 50);
}

/**
 * Prev/next neighbours of a sales order within its project's list - the same set, in the
 * same order, that `/projects/{id}/sales-orders` returns. Read by the generic
 * `useRecordNeighbours` hook.
 *
 *   GET /api/v1/project-sales/projects/{project_id}/sales-orders/neighbours?id=<pso_id>
 *   200 { total, index, prev_id, next_id }
 *       - index is 1-based, null when the order belongs to another project.
 *       - prev_id/next_id wrap circularly; null only when total <= 1.
 *   404 when the project or the sales order id names nothing.
 */
export function salesOrderNeighboursPath(projectId: string): string {
  return `${BASE}/projects/${projectId}/sales-orders/neighbours`;
}

export async function listProjectSalesOrders(
  projectId: string,
  params: ProjectSalesOrderListParams = {},
): Promise<SalesOrderListEnvelope> {
  if (PROJECT_SO_MOCK) return mockList();
  const limit = params.limit ?? 25;
  const search = buildDataGridParams(
    {
      pageIndex: (params.page ?? 1) - 1,
      pageSize: limit,
      sorting: params.sort ? [{ id: params.sort, desc: params.dir === 'desc' }] : [],
      searchQuery: params.query ?? '',
    },
    { status: params.status, purchase_order_id: params.purchase_order_id },
  );
  const response = await apiFetch(
    `${BASE}/projects/${projectId}/sales-orders?${search.toString()}`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the sales orders'));
  return normaliseEnvelope(await response.json(), limit);
}

export async function getProjectSalesOrder(psoId: string): Promise<ProjectSalesOrderDetail> {
  if (PROJECT_SO_MOCK) return mockDetail(psoId);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this sales order'));
  return response.json();
}

/** The reason is mandatory and stays on the sales order forever. */
export async function acknowledgeFinding(
  psoId: string,
  findingId: string,
  reason: string,
): Promise<ProjectSalesOrderDetail> {
  const response = await apiFetch(
    `${BASE}/sales-orders/${psoId}/findings/${findingId}/acknowledge`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to record the acknowledgement'));
  return response.json();
}

export async function updateSalesOrderLine(
  psoId: string,
  lineId: string,
  body: SalesOrderLineUpdateBody,
): Promise<ProjectSalesOrderDetail> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/lines/${lineId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the line'));
  return response.json();
}

/**
 * The whole sales order in ONE write: the header, and the full desired line set.
 *
 * API CONTRACT (SO edit view). The same shape the customer PO's own edit view already saves
 * through (`PUT /purchase-orders/{po_id}`, `project_po_service.save_po_document`), because
 * the two screens are the same screen with different columns and a second dialect would be a
 * second thing to keep in step.
 *
 *   PUT /api/v1/project-sales/sales-orders/{pso_id}
 *   {
 *     area_group?: string | null,          // absent leaves it alone; null clears it
 *     lines?: [                            // absent leaves the lines alone
 *       { id?, product_id?, description?, qty, uom?, unit_price, delivery_date?,
 *         stock_location? }
 *     ]
 *   }
 *   200 ProjectSalesOrderDetail            // the same body GET /sales-orders/{id} answers
 *
 * What the backend guarantees, each pinned by a test in
 * `sorento_crm_backend/tests/test_project_so_document_save.py`:
 * - `lines` is the FULL set. A stored line whose id is absent is DELETED, so a caller that
 *   sends only the rows it touched wipes the rest.
 * - `line_no` is array position; any sent is ignored. `amount` is recomputed as
 *   `qty * unit_price` and cannot be supplied.
 * - the order's `total_amount` and `status` are recomputed once, at the end.
 * - `provisional_ref`, `purchase_order_id`, `schedule_version_id`, and every line's
 *   `phase_id` / `source_po_line_id` / `quotation_line_id` / `core_sales_order_line_id` are
 *   preserved on a kept line: only the fields above are written.
 * - renaming `area_group` moves `grouping_origin` to `manual`, exactly as Move lines does,
 *   because the origin is what says which namespace the group name lives in.
 * - a PUBLISHED or AMENDED order is refused 409 `so_not_editable`: it is in AutoCount, and
 *   the way to change it is an amendment carrying an order change notice.
 * - an empty `lines` array is refused 422 `so_lines_required`: an order with no lines is not
 *   a proposal.
 */
export async function saveSalesOrderDocument(
  psoId: string,
  body: SalesOrderDocumentSaveBody,
): Promise<ProjectSalesOrderDetail> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save this sales order'));
  return response.json();
}

/**
 * Hard delete, so a draft that was built wrong can be built again.
 *
 *   DELETE /api/v1/project-sales/sales-orders/{pso_id}
 *   200 { success: true, provisional_ref, deleted: { "<table>": <rows> } }
 *
 * It takes the order's lines and everything hanging off them with it (findings,
 * allocations, claims, inquiries and their rows, amendments and their change notices,
 * divergences and their compared rows, superseded supply decisions).
 *
 * It REFUSES, 409, anything that is a live commitment rather than a proposal: a published or
 * amended order (`so_published_not_deletable`), one linked to an AutoCount document
 * (`so_autocount_linked`), one carrying a published amendment (`so_amendment_published`), and
 * one whose supply has been confirmed (`so_supply_confirmed`). Those are amended, never
 * deleted.
 */
export async function deleteProjectSalesOrder(
  psoId: string,
): Promise<SalesOrderDeleteResult> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}`, { method: 'DELETE' });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete this sales order'));
  return response.json();
}

/**
 * Several selected drafts in ONE call.
 *
 *   POST /api/v1/project-sales/sales-orders/bulk-delete   { ids: [...] }
 *   200 { success, deleted_count, deleted: { "<table>": n }, refused: [] }
 *
 * ONE call rather than one per row, and it is not an optimisation: N calls half-apply, so
 * the first refusal would leave the reviewer with a selection that is partly gone and no way
 * to say which part. This is ALL OR NOTHING - one undeletable order in the selection refuses
 * the whole call with 409 and deletes nothing, and the message names every order to un-tick
 * and why. `extractApiError` surfaces that sentence, which is what the toast shows.
 *
 * Every id must belong to one project (422 `so_bulk_cross_project`), and the batch is capped
 * at 200 (422 beyond it). The same refusals the single delete raises apply per order:
 * published or amended, AutoCount-linked, carrying a published amendment, supply confirmed.
 */
export async function bulkDeleteProjectSalesOrders(
  ids: string[],
): Promise<SalesOrderBulkDeleteResult> {
  const response = await apiFetch(`${BASE}/sales-orders/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to delete the selected sales orders'),
    );
  return response.json();
}

export async function regroupSalesOrder(
  psoId: string,
  groups: SalesOrderRegroupGroup[],
): Promise<SalesOrderListEnvelope> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/regroup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ groups }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to re-split the lines'));
  return normaliseEnvelope(await response.json(), 50);
}

/**
 * 409 when a hard finding is unacknowledged; the message lists what is blocking.
 *
 * API CONTRACT
 *
 *   POST /api/v1/project-sales/sales-orders/{pso_id}/publish
 *   { acknowledge_blocking?: boolean, reason?: string }   // body optional
 *   200 { status, provisional_ref, import_file_url, can_export, total_amount, line_count,
 *         acknowledged_findings }
 *
 * With `acknowledge_blocking` every open hard finding is acknowledged under the given reason
 * and the order publishes: 403 without the sales-manager grant, 422 on a reason under 3
 * characters. Already published, awaiting costing and no lines still refuse either way.
 */
export async function publishSalesOrder(
  psoId: string,
  body?: SalesOrderPublishBody,
): Promise<SalesOrderPublishResult> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/publish`, {
    method: 'POST',
    ...(body
      ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : {}),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to publish this sales order'));
  return response.json();
}

// -------------------------------------------------------- Stage 1A: the worksheet

/**
 * The AutoCount SO worksheet for one Project SO.
 *
 * API CONTRACT (Stage 1A, PLAN-scm-front-planning sections 1.2 steps 1-3 and 2). Built in
 * Phase 2 to this exact shape and live since; `ProjectSODraftService.worksheet` is the one
 * builder behind both this and the CSV `import_file` writes, so the screen and the
 * downloaded file cannot describe different orders.
 *
 *   GET /api/v1/project-sales/sales-orders/{pso_id}/worksheet
 *   200 {
 *     id, provisional_ref, autocount_doc_no, status, area_group, po_number, customer_name,
 *     header: { debtor, your_ref_no, our_ref_no, our_qt_ref_no, terms },
 *     lines: [{ line_no, item_code, description, reserve_qty, qty, delivery_date, uom,
 *               unit_price, discount, total }],
 *     total_amount,
 *     findings: SODraftFindingRow[],
 *     can_export: boolean,
 *     import_file_url: string | null
 *   }
 *
 * Notes the backend honours, each pinned by a test in
 * `sorento_crm_backend/tests/test_project_so_worksheet.py`:
 * - `lines` is in AutoCount's column order and in `line_no` order; the screen does not sort.
 * - `reserve_qty` is "0" on every row until Stage 1C confirms a supply source.
 * - money and quantities are decimal STRINGS, never numbers.
 * - `can_export` is false while the order is unpublished or carries an unacknowledged hard
 *   finding, so the FE never has to re-derive the rule.
 * - `import_file_url` is null until the order is published.
 * - 404 when the order does not exist, as the sibling routes do.
 */
export async function getSalesOrderWorksheet(psoId: string): Promise<SalesOrderWorksheet> {
  if (PROJECT_SO_MOCK) return mockWorksheet(psoId);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/worksheet`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the AutoCount worksheet'));
  return response.json();
}

/**
 * The stage 1 AutoCount import file, fetched rather than linked to.
 *
 * `import_file_url` is a path on the BACKEND. Given to an anchor it resolves against the
 * frontend origin, where nothing serves it, so the download 404s; the route also wants the
 * bearer token, which a plain link does not carry. Generated per request exactly as the
 * corrective file is: a stored copy goes stale the moment an amendment publishes.
 *
 * The filename is the one the backend stamped on the response; the caller supplies a
 * fallback for a response that carries no `Content-Disposition`.
 *
 * The export gate is the SERVER's: an order that is not published, or is published and
 * still carries an unacknowledged hard finding, answers 422 `so_export_blocked` here. The
 * screens disable their download on the same `can_export` flag so the refusal is visible
 * before the click, but this call is what actually enforces it.
 */
export async function downloadSalesOrderImportFile(
  psoId: string,
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/import-file`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to download the import file'));
  return {
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get('Content-Disposition')),
  };
}

// -------------------------------------------------------------- P11: amendments

/** Writes nothing. */
export async function previewAmendment(
  psoId: string,
  body: AmendmentPreviewBody,
): Promise<AmendmentPreview> {
  if (PROJECT_SO_MOCK) return mockPreview(body);
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/amendments/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to compare the two versions'));
  return response.json();
}

export async function createAmendment(
  psoId: string,
  body: AmendmentCreateBody,
): Promise<AmendmentCreated> {
  const response = await apiFetch(`${BASE}/sales-orders/${psoId}/amendments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to create the amendment'));
  return response.json();
}

export async function getAmendment(amendmentId: string): Promise<AmendmentDetail> {
  const response = await apiFetch(`${BASE}/amendments/${amendmentId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this amendment'));
  return response.json();
}

export async function publishAmendment(amendmentId: string): Promise<AmendmentDetail> {
  const response = await apiFetch(`${BASE}/amendments/${amendmentId}/publish`, {
    method: 'POST',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to publish this amendment'));
  return response.json();
}

// ------------------------------------------------------------- version pickers

/**
 * NOT IN THE CONTRACT. Sections 4 and 2 define how to read ONE version; neither defines how
 * to list the versions of a PO, and both the build step and the delta step have to offer a
 * choice. These two calls are the guess, kept to a strict subset of the single-version
 * bodies so that pointing them at whatever the backend actually exposes is a one-line change.
 */
export async function listScheduleVersions(poId: string): Promise<ScheduleVersionOption[]> {
  if (PROJECT_SO_MOCK) return MOCK_SCHEDULE_VERSIONS;
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/delivery-schedule-versions`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the delivery schedules'));
  const body = await response.json();
  return Array.isArray(body) ? body : (body?.data ?? []);
}

export async function listPoVersions(poId: string): Promise<PoVersionOption[]> {
  if (PROJECT_SO_MOCK) return MOCK_PO_VERSIONS;
  const response = await apiFetch(`${BASE}/purchase-orders/${poId}/versions`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the PO versions'));
  const body = await response.json();
  return Array.isArray(body) ? body : (body?.data ?? []);
}

// ---------------------------------------------------------------------------
// Fixtures, served only when NEXT_PUBLIC_PROJECT_SO_MOCK=1.
//
// Numbers are from the golden set (Tuju Residences, PO HQ/26/01/121, QT-004188) so the
// screen is exercised against the shapes the client's own documents produce: a TOWER split
// carrying set explosions, a blocked COMMON AREA split, and the early product subset that
// has no area logic at all.
// ---------------------------------------------------------------------------

const MOCK_ROWS: ProjectSalesOrderRow[] = [
  {
    id: 'mock-tower',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: null,
    area_group: 'TOWER',
    status: 'draft',
    grouping_origin: 'area',
    line_count: 99,
    total_amount: '1611107.81',
    hard_findings: 0,
    warn_findings: 2,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
  },
  {
    id: 'mock-common',
    provisional_ref: 'PSO-000124',
    autocount_doc_no: null,
    area_group: 'COMMON AREA',
    status: 'blocked',
    grouping_origin: 'area',
    line_count: 41,
    total_amount: '74677.32',
    hard_findings: 2,
    warn_findings: 1,
    is_pre_order: false,
    is_sponsorship: false,
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    created_at: '2026-04-02T02:15:00',
  },
  {
    id: 'mock-subset',
    provisional_ref: 'PSO-000101',
    autocount_doc_no: 'SO376200',
    area_group: null,
    status: 'published',
    grouping_origin: 'subset',
    line_count: 12,
    total_amount: '48120.00',
    hard_findings: 0,
    warn_findings: 0,
    is_pre_order: true,
    is_sponsorship: false,
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    po_number: 'HQ/26/01/121',
    created_at: '2025-11-07T01:00:00',
    published_at: '2025-11-07T03:20:00',
  },
];

function mockList(): SalesOrderListEnvelope {
  return { data: MOCK_ROWS, total: MOCK_ROWS.length, page: 1, limit: 25 };
}

function mockDetail(psoId: string): ProjectSalesOrderDetail {
  const row = MOCK_ROWS.find((entry) => entry.id === psoId) ?? MOCK_ROWS[0];
  const towerLines: ProjectSalesOrderDetail['lines'] = [
    {
      id: 'l1',
      line_no: 1,
      product_code: 'CB6633',
      description: 'CABANA S/STEEL FLOOR GRATING 6"',
      qty: '600',
      uom: 'UNIT',
      unit_price: '11.16000',
      amount: '6696.00',
      delivery_date: '2026-07-01',
      phase_label: 'Level 2 & 7',
      explosion_source: 'none',
      source_po_line_no: 1,
      stock_location: 'BRW-BB',
    },
    {
      id: 'l2',
      line_no: 2,
      product_code: 'SRT382-6',
      description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
      qty: '135',
      uom: 'UNIT',
      unit_price: '13.77000',
      amount: '1858.95',
      delivery_date: '2026-07-01',
      phase_label: 'Level 2 & 7',
      explosion_source: 'none',
      source_po_line_no: 2,
      stock_location: 'BRW-BB',
    },
    {
      id: 'l3',
      line_no: 3,
      product_code: 'SRTWC8613-RL',
      description: 'SORENTO ONE PIECE WASH DOWN (RIMLESS) WC S-TRAP',
      qty: '135',
      uom: 'SET',
      unit_price: '392.85000',
      amount: '53034.75',
      delivery_date: '2027-01-07',
      phase_label: 'Level 8 & 10',
      explosion_source: 'package',
      source_po_line_no: 9,
      stock_location: 'BRW-BB',
    },
    {
      id: 'l4',
      line_no: 4,
      product_code: 'TPE-9300',
      description: 'FLEXIBLE STRAIGHT CONNECTOR P10 B (4")100MM (PW-136)',
      qty: '135',
      uom: 'UNIT',
      unit_price: '0.00000',
      amount: '0.00',
      delivery_date: '2027-01-07',
      phase_label: 'Level 8 & 10',
      explosion_source: 'package',
      source_po_line_no: 9,
      stock_location: 'BRW-BB',
    },
    {
      id: 'l5',
      line_no: 5,
      product_code: 'SRTWCX8608-RL',
      description: 'SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)',
      qty: '124',
      uom: 'SET',
      unit_price: '305.55000',
      amount: '37888.20',
      delivery_date: '2027-01-07',
      phase_label: 'Level 8 & 10',
      explosion_source: 'package',
      source_po_line_no: 10,
      stock_location: 'BRW-BB',
    },
    {
      id: 'l6',
      line_no: 6,
      product_code: 'SRTWCY8608',
      description: 'SORENTO CLOSE-COUPLED CISTERN ONLY (S-TRAP)',
      qty: '124',
      uom: 'UNIT',
      unit_price: '0.00000',
      amount: '0.00',
      delivery_date: '2027-01-07',
      phase_label: 'Level 8 & 10',
      explosion_source: 'package',
      source_po_line_no: 10,
      stock_location: 'BRW-BB',
    },
    {
      id: 'l7',
      line_no: 7,
      product_code: 'SRTWC8608-SC',
      description: 'SORENTO SRTWC8608-SC SEAT COVER ONLY',
      qty: '124',
      uom: 'UNIT',
      unit_price: '0.00000',
      amount: '0.00',
      delivery_date: '2027-01-07',
      phase_label: 'Level 8 & 10',
      explosion_source: 'package',
      source_po_line_no: 10,
      stock_location: 'BRW-BB',
    },
  ];

  const blocked: ProjectSalesOrderDetail['findings'] = [
    {
      id: 'f1',
      severity: 'hard',
      code: 'line_arithmetic',
      detail: 'Line 4: 351 x 10.00 is 3,510.00 but the PO says 3,150.00.',
      line_id: 'l4',
      line_no: 4,
    },
    {
      id: 'f2',
      severity: 'hard',
      code: 'schedule_short',
      detail:
        'CB6645-NL: the schedule places 702 units but the PO orders 1,053. 351 are unscheduled.',
      line_id: 'l3',
      line_no: 3,
    },
  ];

  const warnings: ProjectSalesOrderDetail['findings'] = [
    {
      id: 'f3',
      severity: 'warn',
      code: 'price_vs_quotation',
      detail: 'SRT382-6 is quoted at 13.20 and ordered at 13.77.',
      line_id: 'l2',
      line_no: 2,
    },
    {
      id: 'f4',
      severity: 'warn',
      code: 'credit_exposure',
      detail:
        'Outstanding 842,100.00 plus this order 1,611,107.81 is above the 2,000,000.00 limit. AR as of 02/04/2026 09:00.',
    },
  ];

  return {
    ...row,
    lines: towerLines,
    findings:
      row.status === 'blocked'
        ? [...blocked, ...warnings.slice(1)]
        : [
            ...warnings.slice(0, 1),
            {
              ...warnings[1],
              acknowledged_by_name: 'Eling',
              acknowledged_reason: 'Approved by finance on 01/04, deposit received.',
              acknowledged_at: '2026-04-01T09:12:00',
            },
          ],
  };
}

const MOCK_SCHEDULE_VERSIONS: ScheduleVersionOption[] = [
  {
    id: 'sched-v1',
    version_no: 1,
    revision_label: 'R1',
    issuer_party_label: 'Buimaco Sdn Bhd',
    schedule_date: '2026-01-19',
    po_version_no: 1,
    extraction_state: 'done',
    confirmed_at: '2026-01-20T02:00:00',
  },
  {
    id: 'sched-v2',
    version_no: 2,
    revision_label: 'REVISED 1 - 23/7/2026',
    issuer_party_label: 'SLG Construction Sdn Bhd',
    schedule_date: '2026-07-23',
    po_version_no: 1,
    extraction_state: 'done',
    confirmed_at: '2026-07-24T01:00:00',
  },
];

const MOCK_PO_VERSIONS: PoVersionOption[] = [
  {
    id: 'po-v1',
    version_no: 1,
    po_number: 'HQ/26/01/121',
    po_date: '2026-01-19',
    extraction_state: 'done',
    confirmed_at: '2026-01-20T01:00:00',
  },
];

function mockPreview(body: AmendmentPreviewBody): AmendmentPreview {
  const dateOnly = body.schedule_version_id !== 'sched-v1';
  const rows = [
    {
      so_line_id: 'l3',
      line_no: 3,
      product_code: 'SRTWC8613-RL',
      description: 'SORENTO ONE PIECE WASH DOWN (RIMLESS) WC S-TRAP',
      verb: 'DELAY',
      field: 'delivery_date',
      from_value: '2026-07-01',
      to_value: '2027-01-07',
      qty: '135',
      phase_label_from: 'Level 2 & 7',
      phase_label_to: 'Level 2 & 7',
    },
    {
      so_line_id: 'l5',
      line_no: 5,
      product_code: 'SRTWCX8608-RL',
      description: 'SORENTO CLOSE COUPLED PEDESTAL (S-TRAP 250MM)',
      verb: 'DELAY',
      field: 'delivery_date',
      from_value: '2026-08-03',
      to_value: '2027-01-21',
      qty: '124',
      phase_label_from: 'Level 8 & 10',
      phase_label_to: 'Level 8 & 10',
    },
  ];
  const extra = dateOnly
    ? []
    : [
        {
          so_line_id: 'l1',
          line_no: 1,
          product_code: 'CB6633',
          description: 'CABANA S/STEEL FLOOR GRATING 6"',
          verb: 'CANCEL BALANCE',
          field: 'qty',
          from_value: '600',
          to_value: '570',
          qty: '30',
          phase_label_from: 'Level 2 & 7',
          phase_label_to: 'Level 2 & 7',
        },
      ];
  return {
    from: { kind: 'schedule_version', id: 'sched-v1', version_no: 1, label: 'R1' },
    to: {
      kind: 'schedule_version',
      id: body.schedule_version_id ?? 'sched-v2',
      version_no: 2,
      label: 'REVISED 1',
    },
    verb_summary: dateOnly ? { DELAY: 2 } : { DELAY: 2, 'CANCEL BALANCE': 1 },
    rows: [...rows, ...extra],
    unmatched: dateOnly
      ? []
      : [
          {
            reason: 'phase not found in the new version',
            detail: 'COMMON AREA row 3 (unlabeled, 08/07/2027) has no counterpart in REVISED 1.',
          },
        ],
  };
}

// --------------------------------------------------------- worksheet fixtures
//
// One fixture per state the worksheet screen has to render, keyed by the order id in the
// URL. `mock-subset`, `mock-tower` and `mock-common` are the same three orders the list
// serves, so the screen is reachable by clicking through from a sales order. `mock-amended`
// and `mock-empty` have no list row and are reached by typing the id into the URL; they
// carry the published-with-findings and no-lines states that the three listed orders do
// not produce.

const MOCK_WORKSHEET_HEADER = {
  debtor: 'Hong Bee Hardware Sdn Bhd',
  your_ref_no: 'HQ/26/01/121',
  our_ref_no: 'Tuju Residences',
  our_qt_ref_no: 'QT-004188 v1',
  terms: '*Net 60 days',
};

/**
 * Two delivery dates, one zero-priced companion, all reserve 0 until Stage 1C.
 *
 * Money is at TWO decimals, unlike the draft-line fixtures above: the worksheet is the CSV,
 * and the backend writes its cells through `_money`, which quantizes. A fixture carrying the
 * line table's 5dp would tune the screen against a string the document never contains.
 */
const MOCK_WORKSHEET_LINES: SalesOrderWorksheet['lines'] = [
  {
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    reserve_qty: '0',
    qty: '600',
    delivery_date: '2026-07-01',
    uom: 'UNIT',
    unit_price: '11.16',
    discount: '',
    total: '6696.00',
  },
  {
    line_no: 2,
    item_code: 'SRT382-6',
    description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
    reserve_qty: '0',
    qty: '135',
    delivery_date: '2026-07-01',
    uom: 'UNIT',
    unit_price: '13.77',
    discount: '',
    total: '1858.95',
  },
  {
    line_no: 3,
    item_code: 'SRTWC8613-RL',
    description: 'SORENTO ONE PIECE WASH DOWN (RIMLESS) WC S-TRAP',
    reserve_qty: '0',
    qty: '135',
    delivery_date: '2027-01-07',
    uom: 'SET',
    unit_price: '392.85',
    discount: '',
    total: '53034.75',
  },
  {
    line_no: 4,
    item_code: 'TPE-9300',
    description: 'FLEXIBLE STRAIGHT CONNECTOR P10 B (4")100MM (PW-136)',
    reserve_qty: '0',
    qty: '135',
    delivery_date: '2027-01-07',
    uom: 'UNIT',
    unit_price: '0.00',
    discount: '',
    total: '0.00',
  },
];

const MOCK_WORKSHEET_BLOCKING: SalesOrderWorksheet['findings'] = [
  {
    id: 'wf1',
    severity: 'hard',
    code: 'line_arithmetic',
    detail: 'Line 4: 351 x 10.00 is 3,510.00 but the PO says 3,150.00.',
    line_no: 4,
  },
  {
    id: 'wf2',
    severity: 'hard',
    code: 'schedule_short',
    detail:
      'CB6645-NL: the schedule places 702 units but the PO orders 1,053. 351 are unscheduled.',
    line_no: 3,
  },
];

const MOCK_WORKSHEET_WARNING: SalesOrderWorksheet['findings'] = [
  {
    id: 'wf3',
    severity: 'warn',
    code: 'price_vs_quotation',
    detail: 'SRT382-6 is quoted at 13.20 and ordered at 13.77.',
    line_no: 2,
  },
];

function mockWorksheet(psoId: string): SalesOrderWorksheet {
  const base: SalesOrderWorksheet = {
    id: psoId,
    provisional_ref: 'PSO-000101',
    autocount_doc_no: 'SO376200',
    status: 'published',
    area_group: null,
    po_number: 'HQ/26/01/121',
    customer_name: 'Hong Bee Hardware Sdn Bhd',
    header: MOCK_WORKSHEET_HEADER,
    lines: MOCK_WORKSHEET_LINES,
    total_amount: '61589.70',
    findings: MOCK_WORKSHEET_WARNING,
    can_export: true,
    import_file_url: '/mock/PSO-000101.csv',
  };

  if (psoId === 'mock-tower') {
    return {
      ...base,
      provisional_ref: 'PSO-000123',
      autocount_doc_no: null,
      status: 'draft',
      area_group: 'TOWER',
      customer_name: 'Buimaco Sdn Bhd (Project)',
      header: { ...MOCK_WORKSHEET_HEADER, debtor: 'Buimaco Sdn Bhd (Project)' },
      can_export: false,
      import_file_url: null,
    };
  }

  if (psoId === 'mock-common') {
    return {
      ...base,
      provisional_ref: 'PSO-000124',
      autocount_doc_no: null,
      status: 'blocked',
      area_group: 'COMMON AREA',
      customer_name: 'Buimaco Sdn Bhd (Project)',
      header: { ...MOCK_WORKSHEET_HEADER, debtor: 'Buimaco Sdn Bhd (Project)' },
      lines: MOCK_WORKSHEET_LINES.slice(0, 2),
      total_amount: '8554.95',
      findings: [...MOCK_WORKSHEET_BLOCKING, ...MOCK_WORKSHEET_WARNING],
      can_export: false,
      import_file_url: null,
    };
  }

  // Published, and still carrying a hard finding: the file exists, the export is refused.
  if (psoId === 'mock-amended') {
    return {
      ...base,
      provisional_ref: 'PSO-000102',
      autocount_doc_no: 'SO376244',
      status: 'amended',
      findings: [MOCK_WORKSHEET_BLOCKING[0], ...MOCK_WORKSHEET_WARNING],
      can_export: false,
    };
  }

  if (psoId === 'mock-empty') {
    return {
      ...base,
      provisional_ref: 'PSO-000103',
      autocount_doc_no: null,
      lines: [],
      total_amount: '0.00',
      findings: [],
      can_export: false,
      import_file_url: null,
    };
  }

  return base;
}
