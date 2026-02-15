/**
 * Shared API client utilities: error extraction, DataGrid params, and request helpers.
 * See docs/ADR-PRODUCT-STANDARDS.md for usage guidelines.
 */

import type { SortingState } from '@tanstack/react-table';

export type DataGridParamsInput = {
  pageIndex: number;
  pageSize: number;
  sorting?: SortingState;
  searchQuery?: string;
};

/**
 * Extract user-facing error message from API error response.
 * Handles FastAPI detail (string | array) and common message shapes.
 */
export async function extractApiError(
  response: Response,
  fallbackMessage = 'An error occurred'
): Promise<string> {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const text = await response.text().catch(() => '');
    if (text) return text.slice(0, 300);
    if (response.status === 401) return 'Not signed in or session expired. Please sign in again.';
    if (response.status === 413) return 'File too large. Try a smaller file or ask your admin to increase upload limits.';
    if (response.status >= 500) return 'Server error. Try again or contact support.';
    return fallbackMessage;
  }
  const error = await response.json().catch(() => ({}));
  const detail = error.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    return typeof first === 'string' ? first : (first?.msg ?? first?.message ?? JSON.stringify(first));
  }
  if (detail && typeof detail === 'object' && detail.message) return String(detail.message);
  if (error.message) return String(error.message);
  if (response.status === 401) return 'Not signed in or session expired. Please sign in again.';
  if (response.status >= 500) return 'Server error. Try again or contact support.';
  return fallbackMessage;
}

/**
 * Build URLSearchParams for DataGrid-backed list endpoints.
 * Uses page (1-based), limit, sort, dir, query, plus any extra params.
 */
export function buildDataGridParams(
  params: DataGridParamsInput,
  extra?: Record<string, string | number | boolean | undefined | null>
): URLSearchParams {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const sp = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== null && v !== '') {
        sp.set(k, String(v));
      }
    }
  }
  return sp;
}
