/**
 * The portal Conversation view (lane SALES-CONVO, PLAN-sales-conversation-view-30sep.md): the
 * WhatsApp conversations of the customers assigned to the contact's linked sales agent,
 * read-only. Same gate as Customer asks (linked agent AND the per-contact `conversation`
 * switch; 403 `NOT_A_SALES_AGENT` / `FORM_TYPE_NOT_VISIBLE`).
 *
 * API CONTRACT (`app/api/v1/public/portal_conversations.py`):
 *   GET /api/v1/public/portal/conversations?page=&limit=&q=
 *     -> { data: PortalConversation[], pagination: { total, page, limit } }, latest message first
 *   GET /api/v1/public/portal/conversations/{contact_id}/page?before|after|around&limit
 *     -> the CRM's contact thread page (ConversationThreadPage), same core, same shape
 *   GET /api/v1/public/portal/conversations/{contact_id}/search?q=&limit=
 *     -> { items: ConversationSearchMatch[] }
 *   GET /api/v1/public/portal/conversations/{contact_id}/comments -> ConversationCommentRenderable[]
 * A contact outside the agent's customers is a 404 on the three thread reads.
 */
import { buildDataGridParams } from '@/lib/api-client';
import type {
  ConversationSearchMatch,
  ConversationThreadPage,
} from '@/components/common/conversation/useConversationThread';
import type { ConversationCommentRenderable } from '@/components/common/RespondChatList';
import { NotASalesAgentError } from './customer-asks-service';
import { portalFetch, unwrap } from './portal-client';

const BASE = '/api/v1/public/portal/conversations';

export interface PortalConversation {
  /** `respond_contacts.id`, the key the thread is opened by. Never shown. */
  contact_id: string;
  customer_name: string | null;
  customer_code: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  /** Naive UTC ISO stamp of the latest message. */
  last_message_at: string | null;
  last_message_snippet: string | null;
  /** `incoming` (the customer wrote last) or `outgoing`. */
  last_message_direction: 'incoming' | 'outgoing' | null;
}

export interface PortalConversationPage {
  data: PortalConversation[];
  pagination: { total: number; page: number; limit: number };
}

/** The list is small (an agent's customers with a chat), so one read holds it all. */
export const CONVERSATION_LIST_LIMIT = 200;

export async function listConversations(params: {
  page: number;
  limit: number;
  q?: string;
}): Promise<PortalConversationPage> {
  const usp = buildDataGridParams(
    { pageIndex: params.page - 1, pageSize: params.limit },
    { q: params.q?.trim() || undefined },
  );
  const res = await portalFetch(`${BASE}?${usp.toString()}`);
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<PortalConversationPage>(res, 'Failed to load conversations');
}

export async function getConversationPage(
  contactId: string,
  params: {
    before?: string;
    after?: string;
    around?: string;
    limit?: number;
  } = {},
): Promise<ConversationThreadPage> {
  const sp = new URLSearchParams();
  if (params.before) sp.set('before', params.before);
  if (params.after) sp.set('after', params.after);
  if (params.around) sp.set('around', params.around);
  if (params.limit != null) sp.set('limit', String(params.limit));
  const qs = sp.toString();
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(contactId)}/page${qs ? `?${qs}` : ''}`,
  );
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<ConversationThreadPage>(res, 'Failed to load the conversation');
}

export async function searchConversation(
  contactId: string,
  query: string,
  limit = 100,
): Promise<ConversationSearchMatch[]> {
  const sp = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(contactId)}/search?${sp.toString()}`,
  );
  if (res.status === 403) throw new NotASalesAgentError();
  const body = await unwrap<{ items?: ConversationSearchMatch[] }>(
    res,
    'Search failed',
  );
  return body.items ?? [];
}

export async function getConversationComments(
  contactId: string,
): Promise<ConversationCommentRenderable[]> {
  const res = await portalFetch(
    `${BASE}/${encodeURIComponent(contactId)}/comments`,
  );
  if (res.status === 403) throw new NotASalesAgentError();
  return unwrap<ConversationCommentRenderable[]>(
    res,
    'Failed to load the notes',
  );
}
