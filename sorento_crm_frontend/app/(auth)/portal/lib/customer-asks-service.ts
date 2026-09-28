/**
 * Chatbot stock ask v2 S6: the portal's Customer asks, for a contact linked to a sales
 * agent. The same rows (and the same `state` / `note`) the CRM customer's Asks tab works.
 */
import { portalFetch, unwrap } from './portal-client';
import type { StockAsk, StockAskPage, StockAskPatch, StockAskState } from '@/lib/stock-asks';

const BASE = '/api/v1/public/portal/customer-asks';

/** The contact is not linked to a sales agent (403 `NOT_A_SALES_AGENT`). */
export class NotASalesAgentError extends Error {
  constructor() {
    super('Customer asks are for sales agents only.');
    this.name = 'NotASalesAgentError';
  }
}

export async function listCustomerAsks(params: {
  page: number;
  limit: number;
  q?: string;
  state?: StockAskState;
}): Promise<StockAskPage> {
  const usp = new URLSearchParams({ page: String(params.page), limit: String(params.limit) });
  if (params.q && params.q.trim()) usp.set('q', params.q.trim());
  if (params.state) usp.set('state', params.state);
  const res = await portalFetch(`${BASE}?${usp.toString()}`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<StockAskPage>(res, 'Failed to load customer asks');
}

export async function updateCustomerAsk(askId: string, patch: StockAskPatch): Promise<StockAsk> {
  const res = await portalFetch(`${BASE}/${encodeURIComponent(askId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<StockAsk>(res, 'Failed to update the ask');
}
