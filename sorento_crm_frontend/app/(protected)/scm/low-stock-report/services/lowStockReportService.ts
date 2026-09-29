/**
 * The low stock report page's service (PLAN-excel-preview-26sep S1).
 * Layering: hooks (useLowStockView, useLowStockDownload) -> THIS service -> lib/api -> backend.
 *
 *   GET  /api/v1/scm/order-summary/low-stock-view
 *        ?run_id=<opaque>        omitted = the newest completed run
 *        &split=none|supplier|category|supplier_category
 *        &supplier=<key>...      repeated, one per chosen supplier ("No supplier" = blank)
 *        &category=<key>...      repeated, one per chosen category ("No category" = blank)
 *     -> 200 LowStockView (types/lowStockReport.types.ts)
 *
 *   POST /api/v1/scm/order-summary/export
 *        { run_id, format: "low_stock_xlsx", split, suppliers, categories }
 *     -> 200 MyDownload (pending); the worker builds the file, the page saves it when ready.
 *
 * Both behind `scm.dashboard.view` for a signed-in user. Not a DataGrid listing, so no
 * `buildDataGridParams`: the query is a split and two repeated filters, nothing else.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { MyDownload } from '@/services/myDownloadsService';
import type { LowStockRequest, LowStockView } from '../types/lowStockReport.types';

export async function getLowStockView(request: LowStockRequest): Promise<LowStockView> {
  const params = new URLSearchParams();
  if (request.runId) params.set('run_id', request.runId);
  params.set('split', request.split);
  request.suppliers.forEach((key) => params.append('supplier', key));
  request.categories.forEach((key) => params.append('category', key));
  const res = await apiFetch(`/api/v1/scm/order-summary/low-stock-view?${params}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the low stock report'));
  return (await res.json()) as LowStockView;
}

/** Starts the file through My Downloads with exactly the page's split and filters. */
export async function exportLowStockReport(
  request: LowStockRequest & { runId: string },
): Promise<MyDownload> {
  const res = await apiFetch('/api/v1/scm/order-summary/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      run_id: request.runId,
      format: 'low_stock_xlsx',
      split: request.split,
      suppliers: request.suppliers,
      categories: request.categories,
    }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to start the low stock report'));
  return (await res.json()) as MyDownload;
}
