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
 *           follow_up } -> SalesAgent    gated `master_data.sales_agents.edit`
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
  MirrorAnnotationPayload,
  SalesAgent,
  SalesAgentBulkAnnotatePayload,
} from '../types/salesAgent.types';

const BASE = '/api/v1/master-data/sales-agents';

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
