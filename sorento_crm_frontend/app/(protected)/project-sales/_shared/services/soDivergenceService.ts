import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  DivergenceDetail,
  DivergenceListEnvelope,
  DivergenceListParams,
  DivergenceResolution,
  DivergenceSummary,
  IngestResult,
} from '../types/soDivergence.types';

const BASE = '/api/v1/project-sales';

/**
 * Divergence reconciliation (P8a, contract section 6d).
 *
 * A reconciliation is never created from the browser. It is RAISED by an ingest, which is
 * the only moment we learn AutoCount disagrees with us. What this service does is upload
 * the export that triggers one, read it, and record which side won per row.
 */

function normaliseEnvelope(body: unknown, fallbackLimit: number): DivergenceListEnvelope {
  const raw = (body ?? {}) as {
    data?: DivergenceSummary[];
    pagination?: { total?: number; page?: number; limit?: number };
  };
  const rows = Array.isArray(raw.data) ? raw.data : [];
  return {
    data: rows,
    total: raw.pagination?.total ?? rows.length,
    page: raw.pagination?.page ?? 1,
    limit: raw.pagination?.limit ?? fallbackLimit,
  };
}

export async function listDivergences(
  params: DivergenceListParams = {},
): Promise<DivergenceListEnvelope> {
  const limit = params.limit ?? 25;
  const search = new URLSearchParams();
  search.set('page', String(params.page ?? 1));
  search.set('limit', String(limit));
  if (params.status) search.set('status', params.status);
  if (params.project_id) search.set('project_id', params.project_id);

  const response = await apiFetch(`${BASE}/divergences?${search.toString()}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the reconciliations'));
  return normaliseEnvelope(await response.json(), limit);
}

export async function getDivergence(divergenceId: string): Promise<DivergenceDetail> {
  const response = await apiFetch(`${BASE}/divergences/${divergenceId}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load this reconciliation'));
  return response.json();
}

/**
 * Stage 1: the export a CS takes out of AutoCount.
 *
 * `outcome` is the answer even when nothing matched. An unmatched or ambiguous document
 * is a 200 carrying a reason, not an error: the caller has to show a person WHY, and an
 * exception with a generic message cannot.
 */
export async function ingestSalesOrderFile(file: File): Promise<IngestResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiFetch(`${BASE}/sales-orders/ingest-file`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to read that export'));
  return response.json();
}

/** AC-N4 and AC-N7: one side wins on this row, with the reason recorded. */
export async function resolveDivergenceRow(
  divergenceId: string,
  rowId: string,
  resolution: DivergenceResolution,
  reason: string,
): Promise<DivergenceDetail> {
  const response = await apiFetch(
    `${BASE}/divergences/${divergenceId}/rows/${rowId}/resolve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution, reason }),
    },
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to record that decision'));
  return response.json();
}

/**
 * Our values going back to AutoCount, once something was answered KEEP OURS.
 *
 * Generated per request exactly as the original import file is: a stored copy goes stale
 * the moment anything republishes.
 */
export async function downloadCorrectiveImportFile(divergenceId: string): Promise<Blob> {
  const response = await apiFetch(
    `${BASE}/divergences/${divergenceId}/corrective-import-file`,
  );
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to build the corrective file'));
  return response.blob();
}
