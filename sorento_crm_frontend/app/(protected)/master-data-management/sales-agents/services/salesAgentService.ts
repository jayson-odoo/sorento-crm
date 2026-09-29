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
 *           follow_up, is_active, contact_id } -> SalesAgent
 *                                            gated `master_data.sales_agents.edit`
 *           An omitted key is left alone; `null` unsets. An unknown key is a 422, and a
 *           demand class outside the vocabulary is a 400 naming the allowed words.
 *
 * Customers handled by an agent (PLAN-contact-customers-29sep D2), read `.view`, write `.edit`:
 *   GET  /api/v1/master-data/sales-agents/{id}/customers?page&limit&query&sort&dir
 *          -> { data: AgentCustomer[], pagination: { total, page }, empty }
 *          customers whose sales_agent_id is this agent, under the caller's company scope;
 *          `query` matches code or name; default sort `customer_code asc`.
 *   POST /api/v1/master-data/sales-agents/{id}/customers  body { customer_id } -> 200 AgentCustomer
 *          moves the customer to this agent (from another agent too). Inactive agent or a
 *          cross-company pair: 422; unknown customer: 404.
 *   Unassign has NO route: pending action `customer.unassign_sales_agent`, entity type
 *   `customer`, entity id = customer id, payload { sales_agent_id: <agent id> }, reversible
 *   window, permission `master_data.sales_agents.edit`. Parked by `useDeferredRowAction`.
 *   AgentCustomer is `CustomerResponse` plus `region` and `market_segment_code`: the tab shows
 *   both columns and the schema does not carry them today, so S2 adds them (contract addition).
 * PHASE 1: `USE_MOCK` serves the two customer calls from `customerSelectMock.ts`; S2 flips it.
 *
 * There is no create and no delete: rows appear when an upload meets a code nobody
 * holds, and deleting one would orphan the orders that name it.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import {
  assignMockCustomer,
  findMockCustomer,
  mockCustomers,
} from '@/app/(protected)/order-management/customers/services/customerSelectMock';
import type {
  AgentCustomer,
  ContactSelectOption,
  MirrorAnnotationPayload,
  SalesAgent,
  SalesAgentBulkAnnotatePayload,
} from '../types/salesAgent.types';

const BASE = '/api/v1/master-data/sales-agents';
const USE_MOCK = true;
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

/** One agent by id, for the record page at `/master-data-management/sales-agents/{id}`. */
export async function getSalesAgent(id: string): Promise<SalesAgent> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load sales agent'));
  }
  return response.json();
}

/**
 * Set ONE annotation across a selection.
 *
 *   POST /api/v1/master-data/sales-agents/bulk-annotate
 *     body: { sales_agent_ids, demand_class?, location_group? } -> { updated }
 *     gated `master_data.sales_agents.edit`, the same permission as the single-row PATCH.
 *
 * Same key semantics as that PATCH: an omitted field is left alone, `null` clears it. One
 * transaction on the backend, so a class the fulfilment policy cannot weigh - or an id that
 * no longer resolves - leaves the whole selection untouched.
 */
export async function bulkAnnotateSalesAgents(
  data: SalesAgentBulkAnnotatePayload,
): Promise<{ updated: number }> {
  const response = await apiFetch(`${BASE}/bulk-annotate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update the selected agents'));
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

/** The customers this agent handles, one DataGrid page. */
export async function getSalesAgentCustomers(
  agentId: string,
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<AgentCustomer>> {
  if (USE_MOCK) {
    const q = (params.searchQuery ?? '').trim().toLowerCase();
    const desc = params.sorting?.[0]?.desc ?? false;
    const mine = mockCustomers
      .filter((c) => c.sales_agent_id === agentId)
      .filter(
        (c) =>
          !q ||
          c.customer_code.toLowerCase().includes(q) ||
          c.customer_name.toLowerCase().includes(q),
      )
      .sort((a, b) => a.customer_code.localeCompare(b.customer_code) * (desc ? -1 : 1));
    const start = params.pageIndex * params.pageSize;
    return {
      data: mine.slice(start, start + params.pageSize),
      empty: mine.length === 0,
      pagination: { total: mine.length, page: params.pageIndex + 1 },
    };
  }
  const search = buildDataGridParams(params);
  const response = await apiFetch(`${BASE}/${agentId}/customers?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load customers'));
  }
  return response.json();
}

/** Move a customer to this agent. */
export async function assignSalesAgentCustomer(
  agentId: string,
  customerId: string,
): Promise<AgentCustomer> {
  if (USE_MOCK) {
    if (!findMockCustomer(customerId)) throw new Error('Customer not found');
    return assignMockCustomer(customerId, agentId);
  }
  const response = await apiFetch(`${BASE}/${agentId}/customers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id: customerId }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to assign customer'));
  }
  return response.json();
}
