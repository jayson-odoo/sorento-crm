/**
 * Chatbot stock ask v2 S5: the customer's stock asks on the CRM (Asks tab).
 * The portal's Customer asks page reads the same rows through the portal client
 * (`app/(auth)/portal/lib/customer-asks-service.ts`).
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { StockAsk, StockAskPage, StockAskPatch } from '@/lib/stock-asks';
import type { AskAgentSummary, AskTodoPayload } from '@/lib/stock-asks-todo';

const BASE = '/api/v1/order-management/customers';
const SALES_BASE = '/api/v1/sales/customer-asks';

/*
 * Sales-asks-todo S2 (plan 3.4) API CONTRACT, module `sales`, permission `sales.customer_asks.view`
 * (`.edit` gates the PATCH). The agents a caller may pick: everyone with `.view_all`, else the
 * current members of the active teams they lead (plus themselves), else only themselves:
 *   GET   /api/v1/sales/customer-asks/todo[?agent_id=]
 *     -> AskTodoPayload (see `lib/stock-asks-todo.ts`) plus `agent: {code, name} | null`.
 *        No `agent_id`: my list (user -> respond_contact_id -> agent). A user linked to no agent
 *        gets empty arrays and `agent: null` (200, not 403). `agent_id` outside the pickable set:
 *        403 NOT_YOUR_AGENT; unknown agent: 404.
 *        Addition to plan 3.4 (the manager's "All agents" choice, AC-ST210): `agent_id=all`
 *        returns every agent's rows, each StockAsk carrying `agent_code`; every pickable agent's rows (view_all: everyone, a
 *        team leader: their team; a plain user: 403).
 *   GET   /api/v1/sales/customer-asks/agents
 *     -> [{ agent_id, code, name, open, needs_attention }], the pickable agents (view_all: those
 *        with an open ask; a team leader: every current member, 0 allowed; otherwise `[]`, 200),
 *        counted with the same rules as the to-do payload.
 *   PATCH /api/v1/sales/customer-asks/{ask_id}  { state?, note? } -> StockAsk
 *        Scope = the view scope: the ask's customer's agent is in my pickable set (me, my led
 *        team's current members, or everyone with view_all); otherwise 404. A transition
 *        to done stamps `done_at` and the actor (the user id, server side); `done_by` on the wire is
 *        a label (my name), never an id; a transition to open clears both.
 */

export async function listCustomerAsks(
  customerId: string,
  params: { pageIndex: number; pageSize: number },
): Promise<StockAskPage> {
  const qs = buildDataGridParams({ pageIndex: params.pageIndex, pageSize: params.pageSize });
  const response = await apiFetch(`${BASE}/${customerId}/asks?${qs.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load stock asks'));
  return response.json();
}

export async function updateCustomerAsk(
  customerId: string,
  askId: string,
  patch: StockAskPatch,
): Promise<StockAsk> {
  const response = await apiFetch(`${BASE}/${customerId}/asks/${askId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the ask'));
  return response.json();
}

/** The salesperson's to-do (mine, one chosen agent, or 'all' with `sales.customer_asks.view_all`). */
export async function getCustomerAsksTodo(agentId?: string): Promise<AskTodoPayload> {
  const qs = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : '';
  const response = await apiFetch(`${SALES_BASE}/todo${qs}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load customer asks'));
  return response.json();
}

/** The manager's Agent select: every agent with open counts (view_all only). */
export async function listAskAgents(): Promise<AskAgentSummary[]> {
  const response = await apiFetch(`${SALES_BASE}/agents`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load sales agents'));
  return response.json();
}

/** Done, Reopen and Note from the to-do (not scoped to one customer). */
export async function updateSalesAsk(askId: string, patch: StockAskPatch): Promise<StockAsk> {
  const response = await apiFetch(`${SALES_BASE}/${encodeURIComponent(askId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update the ask'));
  return response.json();
}
