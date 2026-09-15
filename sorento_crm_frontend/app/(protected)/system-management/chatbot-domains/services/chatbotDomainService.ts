/**
 * ============================================================================
 * Chatbot Domains service (chatbot turn re-architecture, S5, AC-1560/AC-1561)
 * ============================================================================
 * Layering: UI -> hooks (useChatbotDomains) -> THIS service -> lib/api -> backend.
 *
 *   GET    /api/v1/system/chatbot/domains            list, `system.chat_history.view`
 *   GET    /api/v1/system/chatbot/domains/{id}        one row
 *   POST   /api/v1/system/chatbot/domains             create, `system.chatbot_config.manage`
 *   PUT    /api/v1/system/chatbot/domains/{id}         update, `system.chatbot_config.manage`
 *   DELETE /api/v1/system/chatbot/domains/{id}         hard delete (D7), same grant
 *
 * The list route answers a small reference table (today: 10 rows), not an ever-growing
 * log - one page at `limit=200` is the whole table, same idiom as the MCP tools catalog
 * (`mcpAdminService.listMcpToolsCatalog`), so the modal's list-of-domains props and the
 * list's own client-side search/filter both keep working unchanged from S1.
 *
 * DELETE is an immediate hard delete on the server (no pending-action row) - the
 * countdown below is a CLIENT-ONLY grace window (D7's 10s), same as S1: `run()` starts
 * a toast countdown with Cancel, and only calls the real DELETE once the window lapses
 * uncancelled. A tab closed mid-countdown loses the delete (nothing was sent to the
 * server yet) rather than losing data silently - the same trade every mocked deferred
 * delete made before a real pending-action endpoint existed for it.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ChatbotDomain, ChatbotDomainInput } from '../types/chatbotDomain.types';

const BASE = '/api/v1/system/chatbot/domains';

/** D7's hard-delete grace window (10s). */
export const DELETE_WINDOW_SECONDS = 10;

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

export async function deleteChatbotDomain(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!response.ok && response.status !== 404) {
    throw new Error(await extractApiError(response, 'Failed to delete the domain'));
  }
}
