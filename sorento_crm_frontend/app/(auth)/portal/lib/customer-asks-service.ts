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
 *   GET   /api/v1/public/portal/customer-asks/{id}/conversation  (S3, plan 3.6; ASKS-UX)
 *     -> { messages: [{ id, direction: 'in' | 'out', text, at }], ask_message_id: id | null,
 *          ask_message_ref: <Respond message id> | null }
 *        Same gate and scope as the PATCH. The opened card reads only `ask_message_ref` from it
 *        (the anchor the shared thread highlights); the window rows predate the thread.
 *   GET   /api/v1/public/portal/customer-asks/{id}/conversation/page?before|after|around&limit
 *   GET   /api/v1/public/portal/customer-asks/{id}/conversation/search?q&limit  (ASKS-UX item 3)
 *     -> the SAME shapes as the ticket drawer's `.../conversation-sla-tracking/{id}/conversation/
 *        {page,search}` (`ConversationThreadPage`, `{ items: ConversationSearchMatch[] }`), the
 *        two loaders `useConversationThread` takes. Same gate and scope as the PATCH.
 */
import { buildDataGridParams } from '@/lib/api-client';
import { portalFetch, unwrap } from './portal-client';
import type { StockAsk, StockAskPage, StockAskPatch, StockAskState } from '@/lib/stock-asks';
import type { AskConversation, AskTodoPayload } from '@/lib/stock-asks-todo';
import type {
  ConversationSearchMatch,
  ConversationThreadPage,
} from '@/components/common/conversation/useConversationThread';

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

/** The ask's anchor in its thread (`ask_message_ref`), for the opened card. */
export async function getAskConversation(askId: string): Promise<AskConversation> {
  const res = await portalFetch(`${BASE}/${encodeURIComponent(askId)}/conversation`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<AskConversation>(res, 'Failed to load the conversation');
}

/** One window of the ask's contact thread; no cursor is the live tail. */
export async function getAskConversationPage(
  askId: string,
  params: { before?: string; after?: string; around?: string; limit?: number },
): Promise<ConversationThreadPage> {
  const sp = new URLSearchParams();
  if (params.before) sp.set('before', params.before);
  if (params.after) sp.set('after', params.after);
  if (params.around) sp.set('around', params.around);
  if (params.limit != null) sp.set('limit', String(params.limit));
  const qs = sp.toString();
  const res = await portalFetch(`${BASE}/${encodeURIComponent(askId)}/conversation/page${qs ? `?${qs}` : ''}`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<ConversationThreadPage>(res, 'Failed to load earlier messages');
}

/** In-thread search over the ask's contact thread, newest first. */
export async function searchAskConversation(
  askId: string,
  query: string,
  limit = 100,
): Promise<ConversationSearchMatch[]> {
  const sp = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await portalFetch(`${BASE}/${encodeURIComponent(askId)}/conversation/search?${sp.toString()}`);
  if (res.status === 403) throw new NotASalesAgentError();
  const body = await unwrap<{ items?: ConversationSearchMatch[] }>(res, 'Search failed');
  return body.items ?? [];
}
