/**
 * PHASE 2 - see PLAN-spo-investigation-grid.md (S2) and its acceptance criteria
 * (AC-11..AC-18). Real backend calls, swapped in at this exact file boundary - every
 * caller (`hooks/useSPODocuments.ts`) is untouched, per the plan's Phase 1 promise.
 *
 * ## API contract (as implemented, `app/api/v1/procurement/spo_allocations.py`)
 *
 * `GET /api/v1/procurement/spo-allocations/documents`
 *   Paged header rows grouped by `spo_number`, aggregated in SQL. Query params:
 *   `page`, `limit`, `sort`, `dir`, `query` (SPO number / product contains), `state`
 *   (all|outstanding|completed, default outstanding), `product_id`, `warehouse_id`,
 *   `overdue_only`. Response: `{ data: SPODocumentRow[], pagination: {total,page,limit},
 *   empty }`. Filters match LINES; a document is included when >=1 of its lines
 *   matches (Q10). Needs `procurement.spo_allocations.view`.
 *
 * `GET /api/v1/procurement/spo-allocations/documents/{spo_number}`
 *   The header rollup + every line, computed fields included (`SPODocumentLine`).
 *   `spo_number` travels slash-encoded (Q7) - `encodeURIComponent` here, at the one
 *   place the URL is built; every caller already holds the DECODED value. 404 for an
 *   unknown number. Needs `procurement.spo_allocations.view`.
 *
 * Bulk delete has no route of its own (review B1/B4): the list parks one
 * `spo_document.delete` pending action per selected `spo_number` on the shared
 * `/api/v1/pending-actions` registry (`useDeferredBulkAction`) instead of a bespoke
 * `DELETE /documents` - see `app/services/record_actions.py` for why (a bulk ORM
 * delete keyed on `spo_number` alone bypassed the company-scope filter).
 *
 * `outstanding` line membership is `app.services.scm.spo_supply.open_incoming_clauses()`
 * AND balance > 0, imported server-side - never restated here.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type { SPODocument, SPODocumentListFilters, SPODocumentRow } from '../types/spoDocument.types';

const BASE = '/api/v1/procurement/spo-allocations/documents';

export interface ListSPODocumentsParams extends SPODocumentListFilters {
  pageIndex: number;
  pageSize: number;
  sortField?: string;
  sortDir?: 'asc' | 'desc';
  searchQuery?: string;
}

/** `GET /spo-allocations/documents`. */
export async function listSPODocuments(
  params: ListSPODocumentsParams,
): Promise<DataGridApiResponse<SPODocumentRow>> {
  const search = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting: params.sortField ? [{ id: params.sortField, desc: params.sortDir === 'desc' }] : [],
      searchQuery: params.searchQuery ?? '',
    },
    {
      state: params.state ?? 'outstanding',
      product_id: params.product_id ?? undefined,
      warehouse_id: params.warehouse_id ?? undefined,
      overdue_only: params.overdue_only ? 'true' : undefined,
    },
  );

  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load SPO documents'));
  }
  return response.json();
}

/** `GET /spo-allocations/documents/{spo_number}`.
 *  `spoNumber` is the DECODED value - the caller strips `encodeURIComponent` first;
 *  it is applied here, once, on the way to the wire. */
export async function getSPODocument(spoNumber: string): Promise<SPODocument | null> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(spoNumber)}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the SPO document'));
  }
  return response.json();
}
