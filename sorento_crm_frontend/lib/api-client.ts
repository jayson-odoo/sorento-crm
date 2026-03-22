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

/** Nginx and other proxies often return HTML for 502/503; never show that in toasts. */
function responseBodyLooksLikeHtml(text: string): boolean {
  const t = text.trim().toLowerCase();
  return (
    t.startsWith('<!doctype') ||
    t.startsWith('<html') ||
    (t.includes('<title>') && (t.includes('502') || t.includes('503') || t.includes('504') || t.includes('bad gateway')))
  );
}

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
    if (text && responseBodyLooksLikeHtml(text)) {
      if (response.status === 502) {
        return 'Bad gateway (502). The API server is not responding — check that the backend is running and nginx proxy settings.';
      }
      if (response.status === 503) {
        return 'Service unavailable (503). The API may be starting or overloaded.';
      }
      if (response.status === 504) {
        return 'Gateway timeout (504). The API took too long to respond.';
      }
      return `Server error (${response.status}). The proxy returned an HTML error page; check API logs.`;
    }
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
