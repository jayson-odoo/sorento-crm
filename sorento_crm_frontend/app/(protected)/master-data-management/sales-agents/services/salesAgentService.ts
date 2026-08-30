/**
 * Sales agent master - feature service.
 *
 * Layering: components -> hooks (useSalesAgents) -> THIS service -> lib/api-client.
 *
 * Backend contract (mounted under the `product` module guard):
 *   GET   /api/v1/master-data/sales-agents?page&limit&sort&dir&query
 *           -> { data: SalesAgent[], pagination: { total, page, limit }, empty }
 *           gated `master_data.sales_agents.view`; `query` matches the agent code.
 *   PATCH /api/v1/master-data/sales-agents/{id}/annotation
 *           body: partial { person_label, demand_class, location_group, internal_note,
 *           follow_up, contact_id } -> SalesAgent    gated `master_data.sales_agents.edit`
 *           An omitted key is left alone; `null` unsets. An unknown key is a 422, and a
 *           demand class outside the vocabulary is a 400 naming the allowed words.
 *
 * There is no create and no delete: rows appear when an upload meets a code nobody
 * holds, and deleting one would orphan the orders that name it.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  ContactSelectOption,
  MirrorAnnotationPayload,
  SalesAgent,
} from '../types/salesAgent.types';

const BASE = '/api/v1/master-data/sales-agents';
const CONTACTS = '/api/v1/user-management/contacts';

export async function getSalesAgents(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<SalesAgent>> {
  const search = buildDataGridParams(params);
  const response = await apiFetch(`${BASE}?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load sales agents'));
  }
  return response.json();
}

/**
 * One agent by id. Unused by the list + modal this slice ships, and kept because the
 * AutoCount branch's `[id]` detail page imports exactly this symbol: dropping it would
 * turn that merge into a build failure (see PLAN amendment 11).
 */
export async function getSalesAgent(id: string): Promise<SalesAgent> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load sales agent'));
  }
  return response.json();
}

export async function annotateSalesAgent(
  id: string,
  data: MirrorAnnotationPayload,
): Promise<SalesAgent> {
  const response = await apiFetch(`${BASE}/${id}/annotation`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save sales agent'));
  }
  return response.json();
}

/**
 * Contacts for the "Linked portal contact" picker, searched on the server.
 *
 * Reuses the contacts list rather than adding a second search route for the same
 * table: `query` already spans name, first/last name and phone, which is exactly what
 * "find the salesperson" needs. It is gated on `user_management.contacts.view`, so a
 * role holding only the master-data grants gets an empty list; the modal says so
 * rather than showing a silently blank dropdown, which is the failure this whole
 * slice exists to remove. A second consumer promotes this to a shared
 * `services/contactSelectService.ts`; one does not.
 *
 * The phone is masked here, on the way in, because the only reason it is on screen is
 * to tell two people with the same name apart.
 */
export async function getContactSelect(
  query: string,
  limit = 20,
): Promise<ContactSelectOption[]> {
  const search = new URLSearchParams({
    limit: String(limit),
    sort: 'name',
    dir: 'asc',
  });
  if (query.trim()) search.set('query', query.trim());

  const response = await apiFetch(`${CONTACTS}/?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load contacts'));
  }
  const body: {
    data?: { id: string; name?: string | null; phone_number?: string | null }[];
  } = await response.json();

  return (body.data ?? []).map((c) => ({
    id: c.id,
    name: (c.name ?? '').trim() || maskPhone(c.phone_number) || 'Unnamed contact',
    masked_phone: maskPhone(c.phone_number),
  }));
}

/** Last four digits only: enough to disambiguate, not enough to dial. */
function maskPhone(phone: string | null | undefined): string | null {
  const digits = (phone ?? '').replace(/\D/g, '');
  if (!digits) return null;
  if (digits.length <= 4) return digits;
  return `***${digits.slice(-4)}`;
}
