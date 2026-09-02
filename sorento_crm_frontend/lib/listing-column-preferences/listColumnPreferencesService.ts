import { apiFetch } from '@/lib/api';

/** One TanStack sort entry, as it is persisted. */
export type ListSortEntry = {
  id: string;
  desc: boolean;
};

/**
 * The stored per-user, per-listing blob.
 *
 * Two independent writers share one row: `useListingColumnPreferences` (from inside
 * DataGrid) owns the three column keys, `useListingViewPreferences` (from the page,
 * above the grid) owns `sorting` / `filters` / `filtersVersion`. The PUT therefore
 * MERGES: a key that is absent from the body is left alone, a key that is present
 * and null is cleared. See PLAN-listing-view-memory 3.2.
 */
export type UserListColumnConfigPayload = {
  version?: number;
  columnOrder?: string[] | null;
  columnVisibility?: Record<string, boolean> | null;
  columnSizing?: Record<string, number> | null;
  /** Remembered sort. Typed, because it becomes an ORDER BY on the next request. */
  sorting?: ListSortEntry[] | null;
  /**
   * Remembered filter. Deliberately OPAQUE: the shape belongs to the page that
   * wrote it (Stock Inquiries stores `{ statuses: string[] }`), so neither the
   * shared hook nor the backend ever interprets it.
   */
  filters?: Record<string, unknown> | null;
  /** The page's own filter-shape version, so a page can detect its stale blobs. */
  filtersVersion?: number | null;
  /**
   * S4 (PLAN-scm-reorder-oi-feedback-1sep.md, AC-4.4): the saved view (segment) THIS
   * user wants auto-applied on open, distinct from the listing's PUBLISHED default
   * (`SavedView.is_default`, everyone's). Owned by `SavedViewsMenu`.
   */
  defaultSavedViewId?: string | null;
};

export type UserListColumnConfigResponse = {
  listing_key: string;
  config: UserListColumnConfigPayload | null;
};

const BASE = '/api/v1/list-query/column-config';

export async function getUserListColumnConfig(listingKey: string): Promise<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  const res = await apiFetch(`${BASE}/${encodeURIComponent(key)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to fetch column config');
  }
  return res.json();
}

export async function upsertUserListColumnConfig(
  listingKey: string,
  payload: UserListColumnConfigPayload,
): Promise<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  const res = await apiFetch(`${BASE}/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to save column config');
  }
  return res.json();
}

export async function resetUserListColumnConfig(listingKey: string): Promise<void> {
  const key = (listingKey || '').trim();
  const res = await apiFetch(`${BASE}/${encodeURIComponent(key)}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to reset column config');
  }
}

