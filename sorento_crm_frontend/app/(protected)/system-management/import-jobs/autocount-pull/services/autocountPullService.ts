/**
 * AutoCount pull + review - feature service.
 * Layering: components -> hooks (useAutocountPull) -> THIS service -> lib/api-client -> backend.
 * Routes: `documentation/plans/autocount/PLAN-autocount-pull-review.md` "Routes" table, prefix
 * `/api/v1/autocount/pulls`. SR1 built start / current / status; rows, download.xlsx, compare and
 * confirm are wired here ahead of their own backend (SR3/SR4) - same URL, method and body shape
 * the plan pins, so nothing here needs to change again once those routes exist.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, codedError, extractApiError, type CodedError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  AutocountComparePullResult,
  AutocountPull,
  AutocountPullEntity,
  AutocountPullExcelRow,
  AutocountPullRowsQuery,
} from '../types/autocountPull.types';

// ---- Public service functions ----------------------------------------------------------

export async function startPull(entity: AutocountPullEntity): Promise<AutocountPull> {
  const response = await apiFetch('/api/v1/autocount/pulls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity }),
  });
  if (!response.ok) throw await codedError(response, 'Could not start the pull.');
  return response.json();
}

export async function getCurrentPull(entity: AutocountPullEntity): Promise<AutocountPull | null> {
  const response = await apiFetch(`/api/v1/autocount/pulls/current?entity=${encodeURIComponent(entity)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not check for an open pull.'));
  return response.json();
}

export async function getPull(jobId: string): Promise<AutocountPull> {
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load the pull.'));
  return response.json();
}

export async function getPullRows(
  jobId: string,
  params: AutocountPullRowsQuery,
): Promise<DataGridApiResponse<AutocountPullExcelRow>> {
  const search = buildDataGridParams({ pageIndex: params.pageIndex, pageSize: params.pageSize, searchQuery: params.query });
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/rows?${search.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load the pull rows.'));
  return response.json();
}

export async function downloadPullXlsx(jobId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/download.xlsx`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not download the file.'));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `autocount-pull-${jobId}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function comparePull(
  jobId: string,
  filename: string,
  rows: Record<string, unknown>[],
): Promise<AutocountComparePullResult> {
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, rows }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not compare the file.'));
  return response.json();
}

export async function confirmPull(jobId: string): Promise<AutocountPull> {
  const response = await apiFetch(`/api/v1/autocount/pulls/${jobId}/confirm`, { method: 'POST' });
  if (!response.ok) throw await codedError(response, 'Could not confirm the pull.');
  return response.json();
}

// ---- Start-error toast text (AC-PL-6) --------------------------------------------------

const START_ERROR_MESSAGES: Record<string, string> = {
  PULL_NOT_ENABLED: 'AutoCount pull is not switched on for this company.',
  PUSH_ACTIVE: 'This book now updates automatically.',
  TOO_MANY_BUILDS: 'A pull was just started. Try again in a minute.',
  NOT_CONFIGURED: 'AutoCount connection is not set up for this company.',
  UNREACHABLE: 'AutoCount could not be reached. Try again.',
};

/**
 * Maps a `startPull` refusal to the one line the button's toast shows (AC-PL-6). Every known
 * code gets its own distinct message; an unknown code (S5b) falls back to whatever the server
 * itself said, so a refusal ladder the FE has not been taught yet still reads as a real sentence
 * instead of a generic "not set up" guess.
 */
export function startPullErrorMessage(error: unknown): string {
  const coded = error as CodedError | undefined;
  const code = coded?.code;
  if (code && START_ERROR_MESSAGES[code]) return START_ERROR_MESSAGES[code];
  if (coded?.message) return coded.message;
  return 'Could not start the pull.';
}
