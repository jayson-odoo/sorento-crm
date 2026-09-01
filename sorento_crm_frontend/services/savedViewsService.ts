/* -------------------------------------------------------------------------------------
 * savedViewsService - segments (S4, PLAN-scm-reorder-oi-feedback-1sep.md).
 *
 * Generalised from `reportService.ts`'s `ReportView*` calls: a saved view of a LISTING
 * (filters + sort + visible columns + column order) rather than of a report, keyed by
 * the same `listing_key` the column-config personalization routes already authorise via
 * `_can_view_listing_key`.
 *
 *   GET    /api/v1/list-query/saved-views/{listing_key}          -> { mine, shared }
 *   POST   /api/v1/list-query/saved-views/{listing_key}          body { name, view } -> SavedView
 *   POST   /api/v1/list-query/saved-views/{view_id}/publish      body { is_shared }  -> SavedView
 *   POST   /api/v1/list-query/saved-views/{view_id}/set-default                      -> SavedView
 *
 * Delete is NOT a call here - it runs through the deferred-action pending-actions
 * surface (`useDeferredRowAction`, action key `saved_view.delete`), which is the
 * product's standard for a destructive action (no confirmation dialog, a countdown
 * the server commits).
 * ----------------------------------------------------------------------------------- */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';

export interface SavedViewSortEntry {
  id: string;
  desc: boolean;
}

export interface SavedViewConfig {
  filters: ListQueryFilterGroup | null;
  sort: SavedViewSortEntry[];
  columns: string[];
  column_order: string[];
}

export interface SavedView {
  id: string;
  name: string;
  is_shared: boolean;
  is_default: boolean;
  /** Display name of the owner, never the user id (no UUID reaches the UI). */
  owner_name: string | null;
  view: SavedViewConfig;
}

export interface SavedViews {
  mine: SavedView[];
  shared: SavedView[];
}

export const SAVED_VIEWS_QUERY_KEY = 'saved-views';

const base = (listingKey: string) => `/api/v1/list-query/saved-views/${encodeURIComponent(listingKey)}`;

const jsonInit = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

async function failed(response: Response, fallback: string): Promise<Error> {
  return new Error(await extractApiError(response, fallback));
}

export async function fetchSavedViews(listingKey: string): Promise<SavedViews> {
  const response = await apiFetch(base(listingKey));
  if (!response.ok) throw await failed(response, 'Failed to load the saved views');
  return response.json();
}

export async function createSavedView(
  listingKey: string,
  body: { name: string; view: SavedViewConfig },
): Promise<SavedView> {
  const response = await apiFetch(base(listingKey), jsonInit('POST', body));
  if (!response.ok) throw await failed(response, 'Failed to save the view');
  return response.json();
}

export async function publishSavedView(id: string, isShared: boolean): Promise<SavedView> {
  const response = await apiFetch(
    `/api/v1/list-query/saved-views/${id}/publish`,
    jsonInit('POST', { is_shared: isShared }),
  );
  if (!response.ok) throw await failed(response, 'Failed to publish the view');
  return response.json();
}

export async function setDefaultSavedView(id: string): Promise<SavedView> {
  const response = await apiFetch(`/api/v1/list-query/saved-views/${id}/set-default`, jsonInit('POST'));
  if (!response.ok) throw await failed(response, 'Failed to set the default view');
  return response.json();
}
