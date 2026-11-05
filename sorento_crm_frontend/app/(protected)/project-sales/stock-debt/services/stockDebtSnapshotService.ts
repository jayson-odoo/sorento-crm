/**
 * Stock Debt snapshots: the board frozen at a moment, with a decision per product.
 * UI -> hooks (`useStockDebtSnapshots`) -> THIS service -> lib/api-client -> backend.
 *
 * All routes sit under `/api/v1/project-sales/stock-debt/snapshots` and need
 * `projects.stock_debt.view` (UAC AC-1 to AC-18). There is no delete function: Delete is the
 * deferred action `stock_debt_snapshot.delete` (AC-15), not a service call.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { MyDownload } from '@/services/myDownloadsService';
import { stockDebtFilterBody } from './stockDebtService';
import type { StockDebtExportParams } from './stockDebtService';
import type { StockDebtExportSplit } from '../types/stockDebt.types';
import type {
  Snapshot,
  SnapshotDecisionFilter,
  SnapshotDecisionInput,
  SnapshotLinesResponse,
  SnapshotListResponse,
  SnapshotRow,
  SnapshotRowsResponse,
  PoLinkOptions,
  PoLinkResult,
} from '../types/stockDebtSnapshot.types';

const BASE = '/api/v1/project-sales/stock-debt/snapshots';

export interface SnapshotListParams {
  pageIndex: number;
  pageSize: number;
  /** Matches the snapshot name. */
  query: string;
}

export interface SnapshotRowsParams extends SnapshotListParams {
  decision: SnapshotDecisionFilter;
}

/** Save the board as it is now. `filters` is the object Export sends, minus `split`. */
export async function createSnapshot(input: {
  name: string;
  filters: Omit<StockDebtExportParams, 'split'>;
}): Promise<Snapshot> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: input.name, filters: stockDebtFilterBody(input.filters) }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the snapshot'));
  return (await res.json()) as Snapshot;
}

export async function listSnapshots(params: SnapshotListParams): Promise<SnapshotListResponse> {
  const search = buildDataGridParams({
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    searchQuery: params.query,
  });
  const res = await apiFetch(`${BASE}?${search}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load snapshots'));
  return (await res.json()) as SnapshotListResponse;
}

export async function getSnapshot(id: string): Promise<Snapshot> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the snapshot'));
  return (await res.json()) as Snapshot;
}

export async function listSnapshotRows(
  id: string,
  params: SnapshotRowsParams,
): Promise<SnapshotRowsResponse> {
  const search = buildDataGridParams(
    { pageIndex: params.pageIndex, pageSize: params.pageSize, searchQuery: params.query },
    { decision: params.decision },
  );
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/rows?${search}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the snapshot rows'));
  return (await res.json()) as SnapshotRowsResponse;
}

/** The stored lines of one row: one bucket when `month` is given, every bucket otherwise. */
export async function getSnapshotRowLines(
  id: string,
  rowId: string,
  month?: string,
): Promise<SnapshotLinesResponse> {
  const search = new URLSearchParams();
  if (month) search.set('month', month);
  const query = search.toString();
  const res = await apiFetch(
    `${BASE}/${encodeURIComponent(id)}/rows/${encodeURIComponent(rowId)}/lines${query ? `?${query}` : ''}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the snapshot lines'));
  const body = (await res.json()) as { data?: SnapshotLinesResponse['lines'] };
  return { lines: body.data ?? [] };
}

export async function setSnapshotDecision(
  id: string,
  rowId: string,
  input: SnapshotDecisionInput,
): Promise<SnapshotRow> {
  const res = await apiFetch(
    `${BASE}/${encodeURIComponent(id)}/rows/${encodeURIComponent(rowId)}/decision`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the decision'));
  return (await res.json()) as SnapshotRow;
}

/** Queues the stored snapshot's workbook through My Downloads. */
export async function exportSnapshot(
  id: string,
  input: { split: StockDebtExportSplit; show_aux: boolean },
): Promise<MyDownload> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start the snapshot export'));
  return (await res.json()) as MyDownload;
}

/* ------------------------------------------------------------ PO link (AC-LINK-CRM-UI) */
// All need `projects.stock_debt.link_po`; every write goes to AutoCount through the Shared
// Service and answers per line what AutoCount said.

const PO_LINK_BASE = '/api/v1/project-sales/stock-debt/po-link';

function poLinkUrl(id: string, rowId: string, tail = ''): string {
  return `${BASE}/${encodeURIComponent(id)}/rows/${encodeURIComponent(rowId)}/po-link${tail}`;
}

async function postJson<T>(url: string, body: unknown, fallback: string): Promise<T> {
  const res = await apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

export async function getPoLinkOptions(id: string, rowId: string): Promise<PoLinkOptions> {
  const res = await apiFetch(poLinkUrl(id, rowId));
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the PO lines'));
  return (await res.json()) as PoLinkOptions;
}

export async function linkPoLines(
  id: string,
  rowId: string,
  lines: Array<{ sales_order_line_id: string; po_line_id: string; qty: number }>,
): Promise<{ results: PoLinkResult[] }> {
  return postJson(poLinkUrl(id, rowId, '/link'), { lines }, 'Failed to link to PO');
}

/** Unlink exactly these PO lines (each linked to a line of the row). */
export async function unlinkPoLines(
  id: string,
  rowId: string,
  poLineIds: string[],
): Promise<{ results: PoLinkResult[] }> {
  return postJson(
    poLinkUrl(id, rowId, '/unlink'),
    { po_line_ids: poLineIds },
    'Failed to unlink from PO',
  );
}

export async function relinkPoLines(
  id: string,
  rowId: string,
  moves: Array<{ po_line_id: string; to_sales_order_line_id: string }>,
): Promise<{ results: PoLinkResult[] }> {
  return postJson(poLinkUrl(id, rowId, '/relink'), { moves }, 'Failed to move the PO');
}

/** Move a linked PO line to its sales order line's location. */
export async function relocatePoLine(poLineId: string): Promise<PoLinkResult> {
  return postJson(`${PO_LINK_BASE}/relocate`, { po_line_id: poLineId }, 'Failed to move the PO line');
}

/** Ask the Shared Service to finish an operation it stopped (it re-reads AutoCount first). */
export async function resumePoLink(input: {
  operationId: string;
  poLineId: string;
  salesOrderLineId: string | null;
}): Promise<PoLinkResult> {
  return postJson(
    `${PO_LINK_BASE}/operations/${encodeURIComponent(input.operationId)}/resume`,
    { po_line_id: input.poLineId, sales_order_line_id: input.salesOrderLineId },
    'Failed to resume',
  );
}

/** Whether "AutoCount links from Stock Debt" is on (System Settings, owner 5 Nov), read off
 *  the app-config projection every signed-in user may read. Off: no PO actions at all. */
export async function getPoLinkSwitch(): Promise<boolean> {
  const res = await apiFetch('/api/user-management/settings/app-config');
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load settings'));
  const body = (await res.json()) as { stock_debt_po_link_enabled?: boolean };
  return body.stock_debt_po_link_enabled === true;
}
