/**
 * Chatbot stock ask v2 S6: the portal's Customer asks, for a contact linked to a sales
 * agent. The same rows (and the same `state` / `note`) the CRM customer's Asks tab works.
 *
 * Sales-asks-todo S1 (plan 3.2, 3.5) API CONTRACT, same gate as the list (linked agent AND the
 * per-contact `customer_asks` switch; 403 `NOT_A_SALES_AGENT` / `FORM_TYPE_NOT_VISIBLE`):
 *   GET   /api/v1/public/portal/customer-asks/todo
 *     -> { today_start: ISO UTC of Malaysia midnight, open: StockAsk[] (state open, EVERY branch
 *          including incoming, oldest first, cap 500), done_today: StockAsk[] (done_at >= today_start,
 *          newest first), truncated: boolean }
 *   PATCH /api/v1/public/portal/customer-asks/{id}  { state?, note? }  -> StockAsk
 *          (unchanged route; a transition to done now stamps `done_at` and the actor ids; `done_by` on the wire is the
 *          contact's label, a transition to open clears both, a note-only PATCH touches neither)
 *   GET   /api/v1/public/portal/customer-asks?state=done&page=&limit=  (unchanged, "Show done")
 * `StockAsk` gains `done_at` and `done_by`.
 */
import { buildDataGridParams } from '@/lib/api-client';
import { portalFetch, unwrap } from './portal-client';
import type { StockAsk, StockAskPage, StockAskPatch, StockAskState } from '@/lib/stock-asks';
import type { AskTodoPayload } from '@/lib/stock-asks-todo';

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
  const usp = buildDataGridParams(
    { pageIndex: params.page - 1, pageSize: params.limit },
    { q: params.q?.trim(), state: params.state },
  );
  const res = await portalFetch(`${BASE}?${usp.toString()}`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<StockAskPage>(res, 'Failed to load customer asks');
}

/** The to-do read: one payload, grouped on the client by `bucketTodo`. */
export async function getCustomerAsksTodo(): Promise<AskTodoPayload> {
  const res = await portalFetch(`${BASE}/todo`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<AskTodoPayload>(res, 'Failed to load customer asks');
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
