import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { ImportJob, ImportJobRow, ImportJobRowsQuery } from '../types/importJob.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

/**
 * ── Row-outcome API contract (frozen in Phase 1, implemented in Phase 2) ──────────
 *
 * GET /api/v1/system/jobs/{job_id}/rows
 *   query: page, limit, sort, dir, query, outcome, code
 *   200:   { data: ImportJobRow[], pagination: { total, page, limit }, empty: boolean }
 *   404:   unknown job. A job with no captured rows returns an empty list, not an error.
 *
 * GET /api/v1/system/jobs/{job_id}/rows/export
 *   query: same filters as above (no paging - streams the whole filtered set)
 *   200:   text/csv, Content-Disposition: attachment; filename="import-job-{id}-rows.csv"
 *   columns: row, outcome, code, reason, detail, value, identity, entity_id
 *
 * The per-job aggregate breakdown is NOT a separate call - it rides on
 * GET /jobs/{job_id} in `result.breakdown` (see ImportJobResultEnvelope).
 * ─────────────────────────────────────────────────────────────────────────────────
 */

export async function getImportJobs(
  params: DataGridApiFetchParams & { job_type?: string; status?: string },
): Promise<DataGridApiResponse<ImportJob>> {
  const { pageIndex, pageSize, job_type, status } = params;
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(job_type ? { job_type } : {}),
    ...(status ? { status } : {}),
  });
  const response = await apiFetch(`/api/v1/system/jobs?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch import jobs');
  return response.json();
}

export async function getImportJob(jobId: string): Promise<ImportJob> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}`);
  if (!response.ok) throw new Error('Failed to fetch import job');
  return response.json();
}

export async function getImportJobStatus(jobId: string): Promise<{
  job_id: string;
  status: string;
  progress?: {
    total: number;
    processed: number;
    successful: number;
    failed: number;
    skipped: number;
    percentage: number;
  };
  result?: any;
  error?: string | null;
}> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/status`);
  if (!response.ok) throw new Error('Failed to fetch job status');
  return response.json();
}

export async function getImportJobSourceUrl(
  jobId: string,
): Promise<{ url: string; filename?: string | null; size?: number | null }> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/source`);
  if (!response.ok) throw new Error('Failed to fetch source file link');
  return response.json();
}

export async function getImportJobRows(
  jobId: string,
  params: ImportJobRowsQuery,
): Promise<DataGridApiResponse<ImportJobRow>> {
  const search = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      searchQuery: params.query,
    },
    { outcome: params.outcome, code: params.code },
  );
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/rows?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch import job rows'));
  }
  return response.json();
}

/** URL for the CSV export of the currently filtered rows. */
export function buildImportJobRowsExportPath(
  jobId: string,
  params: Omit<ImportJobRowsQuery, 'pageIndex' | 'pageSize'>,
): string {
  const search = buildDataGridParams(
    { pageIndex: 0, pageSize: 0, searchQuery: params.query },
    { outcome: params.outcome, code: params.code },
  );
  // Paging is meaningless for the export - it streams the whole filtered set.
  search.delete('page');
  search.delete('limit');
  const qs = search.toString();
  return `/api/v1/system/jobs/${jobId}/rows/export${qs ? `?${qs}` : ''}`;
}

export async function downloadImportJobRowsCsv(
  jobId: string,
  params: Omit<ImportJobRowsQuery, 'pageIndex' | 'pageSize'>,
): Promise<Blob> {
  const response = await apiFetch(buildImportJobRowsExportPath(jobId, params));
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to export import job rows'));
  }
  return response.blob();
}

export async function cancelImportJob(jobId: string): Promise<{ message: string }> {
  const response = await apiFetch(`/api/v1/system/jobs/${jobId}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to cancel import job' }));
    throw new Error(error.detail || 'Failed to cancel import job');
  }
  return response.json();
}
