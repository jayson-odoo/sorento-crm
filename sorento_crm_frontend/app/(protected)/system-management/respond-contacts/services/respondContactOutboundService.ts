/** Outbound-switch API for Respond.io contacts.
 *
 * Backend contract (`app/api/v1/system/respond_contacts.py`, permission
 * `system.respond_workspaces.view` to read, `.edit` to write):
 *
 *   GET  /api/v1/system/respond-contacts?page&limit&query&outbound
 *        -> { data: RespondContactOutboundRow[], pagination, empty, counts }
 *        `counts` covers the WHOLE table, not the filtered page.
 *
 *   POST /api/v1/system/respond-contacts/{contact_id}/outbound
 *        body { enabled: boolean } -> RespondContactOutboundRow
 *
 *   POST /api/v1/system/respond-contacts/outbound/bulk
 *        body { enabled: boolean, contact_ids?: string[], all?: boolean }
 *        -> { requested, changed, counts }
 *        Exactly one of `contact_ids` / `all` may be given (422 otherwise).
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type {
  OutboundFilter,
  RespondContactOutboundBulkResult,
  RespondContactOutboundListResponse,
  RespondContactOutboundRow,
} from '../types/respondContactOutbound.types';

const BASE = '/api/v1/system/respond-contacts';

export async function getRespondContactsOutbound(
  params: DataGridApiFetchParams & { outbound?: OutboundFilter },
): Promise<RespondContactOutboundListResponse> {
  const search = buildDataGridParams(params, {
    outbound: params.outbound && params.outbound !== 'all' ? params.outbound : undefined,
  });
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load Respond contacts'));
  }
  return response.json();
}

export async function setContactOutbound(
  contactId: string,
  enabled: boolean,
): Promise<RespondContactOutboundRow> {
  const response = await apiFetch(`${BASE}/${contactId}/outbound`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) {
    throw new Error(
      await extractApiError(
        response,
        enabled ? 'Failed to enable outbound' : 'Failed to disable outbound',
      ),
    );
  }
  return response.json();
}

export async function setBulkOutbound(payload: {
  enabled: boolean;
  contactIds?: string[];
  all?: boolean;
}): Promise<RespondContactOutboundBulkResult> {
  const response = await apiFetch(`${BASE}/outbound/bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enabled: payload.enabled,
      ...(payload.all ? { all: true } : { contact_ids: payload.contactIds ?? [] }),
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update outbound messaging'));
  }
  return response.json();
}
