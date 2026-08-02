import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Shared "requestor" picker source for internal CRM edit forms (purchase request /
 * sponsorship form "Requested by", stock inquiry "Salesperson"). Names only - no
 * UUIDs, no other contact fields - mirroring the portal-side requestor-options
 * contract. See docs/plans/PLAN-requested-by-contact-routing.md §5-6.
 */
export interface RequestorOption {
  id: string;
  name: string;
}

export interface RequestorSelectResponse {
  items: RequestorOption[];
  has_more: boolean;
}

export interface GetRequestorSelectOptionsParams {
  q?: string;
  /**
   * IDs that must always be present in the list even if they belong to no
   * eligible segment: the row's submitting contact, and the currently-saved
   * requestor. Keeps self-service and re-opening a stale row from silently
   * losing the selection.
   */
  includeIds?: (string | null | undefined)[];
}

export async function getRequestorSelectOptions(
  params: GetRequestorSelectOptionsParams = {},
): Promise<RequestorSelectResponse> {
  const sp = new URLSearchParams();
  if (params.q) sp.set('q', params.q);
  const ids = Array.from(
    new Set((params.includeIds ?? []).filter((id): id is string => !!id)),
  );
  if (ids.length > 0) sp.set('include_ids', ids.join(','));
  const qs = sp.toString();
  const response = await apiFetch(
    `/api/v1/master-data/respond-contacts/requestor-select${qs ? `?${qs}` : ''}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load requestor options'));
  }
  return response.json();
}
