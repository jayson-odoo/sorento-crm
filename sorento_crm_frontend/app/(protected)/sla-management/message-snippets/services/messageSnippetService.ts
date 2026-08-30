/**
 * Message snippets - feature service (UAC AC-L4, slice S4.4).
 *
 * Contract: documentation/plans/sla/conversation-intervention-tickets-acceptance-criteria.md
 * Plan:     documentation/plans/sla/PLAN-conversation-intervention-tickets.md (slice S4.4)
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT (as implemented)
 * ---------------------------------------------------------------------------
 * All paths are under `/api/v1/sla-management/message-snippets`.
 *
 * GET  /?page&limit&query&sort&dir&is_active
 *   -> { data: MessageSnippet[], pagination: {total,page,limit}, empty: boolean }
 *   Admin listing: every snippet, active or not. Needs
 *   `sla_management.message_snippets.view`.
 *
 * GET  /select?query=&tracking_id=
 *   -> MessageSnippetOption[]
 *   The composer's "/" picker: ACTIVE snippets only, each carrying both the
 *   stored `body` (with `$tokens`) and a `resolved_body` with this ticket's
 *   context already substituted. Needs only `.view`, so everyone who works
 *   tickets can insert one. With a `tracking_id` the caller must be able to act
 *   on that ticket, otherwise 404 (never 403 - no existence leak).
 *
 * GET    /{id}                       -> MessageSnippet
 * POST   /            body Write     -> MessageSnippet (201). Needs `.add`.
 * PUT    /{id}        body Partial   -> MessageSnippet.  Needs `.edit`.
 * DELETE /{id}                       -> { message }. HARD delete. Needs `.delete`.
 *
 * A duplicate shortcut is a 409; the shortcut is compared case-insensitively
 * and a leading "/" is stripped server-side (the slash is composer syntax, not
 * part of the keyword).
 * ---------------------------------------------------------------------------
 */

import type { SortingState } from '@tanstack/react-table';
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  MessageSnippet,
  MessageSnippetFormData,
  MessageSnippetOption,
} from '../types/messageSnippet.types';

const BASE = '/api/v1/sla-management/message-snippets';

export interface MessageSnippetListQuery {
  pageIndex: number;
  pageSize: number;
  searchQuery?: string;
  sorting?: SortingState;
}

export interface MessageSnippetPage {
  data: MessageSnippet[];
  pagination: { total: number; page: number; limit: number };
  empty?: boolean;
}

export async function listMessageSnippets(
  q: MessageSnippetListQuery,
): Promise<MessageSnippetPage> {
  const params = buildDataGridParams({
    pageIndex: q.pageIndex,
    pageSize: q.pageSize,
    sorting: q.sorting ?? [],
    searchQuery: q.searchQuery ?? '',
  });
  const response = await apiFetch(`${BASE}?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load message snippets'));
  }
  return response.json();
}

export async function createMessageSnippet(
  body: MessageSnippetFormData,
): Promise<MessageSnippet> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create the snippet'));
  }
  return response.json();
}

export async function updateMessageSnippet(
  id: string,
  body: Partial<MessageSnippetFormData>,
): Promise<MessageSnippet> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update the snippet'));
  }
  return response.json();
}

/**
 * The composer picker's list, with every body already resolved against the
 * ticket. Resolution is server-side on purpose: one implementation, and the
 * fallbacks ("Hi there" for a nameless contact) cannot drift between the
 * preview and what the contact receives.
 */
export async function getMessageSnippetOptions(params: {
  trackingId?: string | null;
  query?: string;
}): Promise<MessageSnippetOption[]> {
  const search = new URLSearchParams();
  if (params.trackingId) search.set('tracking_id', params.trackingId);
  if (params.query) search.set('query', params.query);
  const qs = search.toString();
  const response = await apiFetch(`${BASE}/select${qs ? `?${qs}` : ''}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load snippets'));
  }
  return response.json();
}
