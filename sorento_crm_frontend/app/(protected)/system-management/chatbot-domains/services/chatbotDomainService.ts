/**
 * ============================================================================
 * Chatbot Domains service (chatbot turn re-architecture, S5, AC-1560/AC-1561)
 * ============================================================================
 * Layering: UI -> hooks (useChatbotDomains) -> THIS service -> lib/api -> backend.
 *
 *   GET    /api/v1/system/chatbot/domains            list, `system.chat_history.view`
 *   GET    /api/v1/system/chatbot/domains/{id}        one row
 *   GET    /api/v1/system/chatbot/domains/{id}/prompt-block  its parser paragraph
 *   POST   /api/v1/system/chatbot/domains             create, `system.chatbot_config.manage`
 *   PUT    /api/v1/system/chatbot/domains/{id}         update, `system.chatbot_config.manage`
 *   DELETE /api/v1/system/chatbot/domains/{id}         hard delete (D7), same grant
 *
 * The list route answers a small reference table (today: 10 rows), not an ever-growing
 * log - one page at `limit=200` is the whole table, same idiom as the MCP tools catalog
 * (`mcpAdminService.listMcpToolsCatalog`), so the modal's list-of-domains props and the
 * list's own client-side search/filter both keep working unchanged from S1.
 *
 * DELETE is never called from here: `chatbot_domain.delete` is a registered
 * `FormAction`, so the countdown is parked SERVER side through `/api/v1/pending-actions`
 * and the server issues the DELETE itself when the window lapses, even if the tab was
 * closed. `useChatbotDomainDeletion` runs it through `useDeferredRowAction`, the hook
 * every other deferred-delete list uses.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ChatbotDomain, ChatbotDomainInput } from '../types/chatbotDomain.types';

const BASE = '/api/v1/system/chatbot/domains';

interface ChatbotDomainRow extends ChatbotDomainInput {
  id: string;
  updated_at: string;
}

interface ChatbotDomainListResponse {
  data: ChatbotDomainRow[];
  pagination: { total: number; page: number; limit: number };
}

export async function listChatbotDomains(): Promise<ChatbotDomain[]> {
  const response = await apiFetch(`${BASE}?limit=200&sort=sort_order&dir=asc`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load chatbot domains'));
  }
  const body: ChatbotDomainListResponse = await response.json();
  return body.data;
}

export async function getChatbotDomain(id: string): Promise<ChatbotDomain | undefined> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (response.status === 404) return undefined;
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the domain'));
  }
  return response.json();
}

export async function createChatbotDomain(input: ChatbotDomainInput): Promise<ChatbotDomain> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create the domain'));
  }
  return response.json();
}

export async function updateChatbotDomain(
  id: string,
  input: ChatbotDomainInput,
): Promise<ChatbotDomain> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the domain'));
  }
  return response.json();
}

// No `deleteChatbotDomain` here by design: the delete is a server-deferred pending
// action (`chatbot_domain.delete`), so `/api/v1/pending-actions` parks it and the server
// calls `DELETE /system/chatbot/domains/{id}` itself when the window lapses. A second
// client-side delete path would be a way to bypass the grace window.

/**
 * The domain's paragraph as the published parser prompt carries it. Rendered by the
 * backend (`chatbot_parser_prompt.domain_line`, the same function the publish uses), not
 * rebuilt here: a preview that guesses the wording is a second copy of it.
 */
export async function getChatbotDomainPromptBlock(id: string): Promise<string> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(id)}/prompt-block`,
    { method: 'GET' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the prompt block'));
  }
  const body = (await response.json()) as { block: string };
  return body.block ?? '';
}
