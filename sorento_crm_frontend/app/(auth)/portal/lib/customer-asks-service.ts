/**
 * Chatbot stock ask v2 S6: the portal's Customer asks, for a contact linked to a sales
 * agent. The same rows (and the same `state` / `note`) the CRM customer's Asks tab works.
 *
 * Sales-asks-todo S1 (plan 3.2, 3.5) API CONTRACT, same gate as the list (linked agent AND the
 * per-contact `customer_asks` switch; 403 `NOT_A_SALES_AGENT` / `FORM_TYPE_NOT_VISIBLE`):
 *   GET   /api/v1/public/portal/customer-asks/todo
 *     -> { today_start: ISO UTC of Malaysia midnight, open: StockAsk[] (state open, branch not
 *          incoming, oldest first, cap 500), done_today: StockAsk[] (done_at >= today_start,
 *          newest first), truncated: boolean }
 *   PATCH /api/v1/public/portal/customer-asks/{id}  { state?, note? }  -> StockAsk
 *          (unchanged route; a transition to done now stamps `done_at` + `done_by` = the
 *          contact's label, a transition to open clears both, a note-only PATCH touches neither)
 *   GET   /api/v1/public/portal/customer-asks?state=done&page=&limit=  (unchanged, "Show done")
 * `StockAsk` gains `done_at` and `done_by`.
 */
import { buildDataGridParams } from '@/lib/api-client';
import { portalFetch, unwrap } from './portal-client';
import type { StockAsk, StockAskPage, StockAskPatch, StockAskState } from '@/lib/stock-asks';
import type { AskTodoPayload } from '@/lib/stock-asks-todo';
import { getMockAskStore } from '@/lib/stock-asks-todo-mock';

/** PHASE 1 MOCK: true serves the in-memory store; Phase 2 flips it and deletes the mock file. */
const PHASE1_MOCK = true; // PHASE 1 MOCK
const MOCK_ACTOR = 'Sean Ibrahim'; // PHASE 1 MOCK: the contact label the server will stamp

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
  if (PHASE1_MOCK) return getMockAskStore().list(params); // PHASE 1 MOCK
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
  if (PHASE1_MOCK) return getMockAskStore().todo(); // PHASE 1 MOCK
  const res = await portalFetch(`${BASE}/todo`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<AskTodoPayload>(res, 'Failed to load customer asks');
}

export async function updateCustomerAsk(askId: string, patch: StockAskPatch): Promise<StockAsk> {
  if (PHASE1_MOCK) return getMockAskStore().patch(askId, patch, MOCK_ACTOR); // PHASE 1 MOCK
  const res = await portalFetch(`${BASE}/${encodeURIComponent(askId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<StockAsk>(res, 'Failed to update the ask');
}
