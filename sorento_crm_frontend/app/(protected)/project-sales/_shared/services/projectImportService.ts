/**
 * Project import - feature service (PLAN-project-import-12nov.md, "Frontend contract").
 * Layering: UI -> hooks (`useProjectImport`) -> THIS service -> lib/api-client -> backend.
 *
 * Routes (`/api/v1/projects/import`, backend `app/api/v1/projects/project_import.py`):
 *   GET  /runs                      DataGrid + status, uploaded_by (multi)   -> { data, total }
 *   POST /runs                      multipart `file`                          -> run (201)
 *   GET  /runs/{id}                                                           -> run
 *   PUT  /runs/{id}/columns         { sheets, columns }
 *   GET  /runs/{id}/lines           kind, status + DataGrid                   -> { items, total }
 *   GET  /runs/{id}/lines/summary                                             -> { kind: { total, todo } }
 *   PUT  /runs/{id}/lines           one line
 *   PUT  /runs/{id}/lines/bulk      every ticked key in one call
 *   POST /runs/{id}/preview                                                   -> { counts, codes, sheet_errors }
 *   GET  /runs/{id}/rows            DataGrid + outcome, code, sheet (multi)   -> { data, total }
 *   POST /runs/{id}/import                                                    -> { job_id } (202)
 * Revert is the pending action `project_import_run.revert` (useDeferredAction).
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError, type DataGridParamsInput } from '@/lib/api-client';
import type {
  Paged,
  PagedItems,
  ProjectImportBulkBody,
  ProjectImportKind,
  ProjectImportLine,
  ProjectImportLineBody,
  ProjectImportLinesSummary,
  ProjectImportPreviewResult,
  ProjectImportReportRow,
  ProjectImportRun,
  ProjectImportRunRow,
} from '../types/projectImport.types';

const BASE = '/api/v1/projects/import';
const JSON_HEADERS = { 'Content-Type': 'application/json' };

function runUrl(runId: string, path = ''): string {
  return `${BASE}/runs/${encodeURIComponent(runId)}${path}`;
}

async function read<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return response.json();
}

export async function listRuns(
  grid: DataGridParamsInput,
  filters: { status?: string[]; uploaded_by?: string[] } = {},
): Promise<Paged<ProjectImportRunRow>> {
  const search = buildDataGridParams(grid, {
    status: filters.status?.length ? filters.status : undefined,
    uploaded_by: filters.uploaded_by?.length ? filters.uploaded_by : undefined,
  });
  return read(await apiFetch(`${BASE}/runs?${search.toString()}`), 'Failed to load imports');
}

export async function getRun(runId: string): Promise<ProjectImportRun> {
  return read(await apiFetch(runUrl(runId)), 'Failed to load this import');
}

export async function createRun(file: File): Promise<ProjectImportRun> {
  const body = new FormData();
  body.append('file', file);
  return read(
    await apiFetch(`${BASE}/runs`, { method: 'POST', body }),
    'The file could not be uploaded',
  );
}

export async function saveColumns(
  runId: string,
  body: { sheets: string[]; columns: Record<string, string> },
): Promise<ProjectImportRun> {
  return read(
    await apiFetch(runUrl(runId, '/columns'), {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
    'Failed to save the columns',
  );
}

export async function listLines(
  runId: string,
  kind: ProjectImportKind,
  grid: DataGridParamsInput,
  filters: { status?: 'todo' | 'set' | string[] } = {},
): Promise<PagedItems<ProjectImportLine>> {
  const status = Array.isArray(filters.status) && !filters.status.length ? undefined : filters.status;
  const search = buildDataGridParams(grid, { kind, status });
  return read(
    await apiFetch(`${runUrl(runId, '/lines')}?${search.toString()}`),
    'Failed to load the values',
  );
}

export async function getLinesSummary(runId: string): Promise<ProjectImportLinesSummary> {
  return read(await apiFetch(runUrl(runId, '/lines/summary')), 'Failed to load the values');
}

export async function setLine(
  runId: string,
  body: ProjectImportLineBody,
): Promise<ProjectImportLine> {
  return read(
    await apiFetch(runUrl(runId, '/lines'), {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
    'Failed to save the value',
  );
}

export async function bulkSetLines(
  runId: string,
  body: ProjectImportBulkBody,
): Promise<{ data: ProjectImportLine[] }> {
  return read(
    await apiFetch(runUrl(runId, '/lines/bulk'), {
      method: 'PUT',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
    'Failed to save the values',
  );
}

export async function previewRun(runId: string): Promise<ProjectImportPreviewResult> {
  return read(
    await apiFetch(runUrl(runId, '/preview'), { method: 'POST' }),
    'The preview could not run',
  );
}

export async function listRows(
  runId: string,
  grid: DataGridParamsInput,
  filters: { outcome?: string[]; code?: string[]; sheet?: string[] } = {},
): Promise<Paged<ProjectImportReportRow>> {
  const search = buildDataGridParams(grid, {
    outcome: filters.outcome?.length ? filters.outcome : undefined,
    code: filters.code?.length ? filters.code : undefined,
    sheet: filters.sheet?.length ? filters.sheet : undefined,
  });
  return read(
    await apiFetch(`${runUrl(runId, '/rows')}?${search.toString()}`),
    'Failed to load the rows',
  );
}

export async function startImport(runId: string): Promise<{ job_id: string }> {
  return read(
    await apiFetch(runUrl(runId, '/import'), { method: 'POST' }),
    'The import could not start',
  );
}
