import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ChatHistoryFilters,
  ChatMessageListResponse,
  ChatThreadResponse,
} from '../types/chatHistory.types';

function buildParams(filters: ChatHistoryFilters, extra: Record<string, string | number | undefined> = {}) {
  const params = new URLSearchParams();
  Object.entries({ ...filters, ...extra }).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '' || value === false) return;
    params.set(key, String(value));
  });
  return params;
}

export async function getChatMessages(
  filters: ChatHistoryFilters,
  opts: { limit?: number; cursor?: string | null } = {},
): Promise<ChatMessageListResponse> {
  const params = buildParams(filters, {
    limit: opts.limit ?? 50,
    cursor: opts.cursor ?? undefined,
  });
  const response = await apiFetch(`/api/v1/system/chat-history?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load chat messages'));
  return response.json();
}

export async function getChatThread(
  contactId: string,
  anchorId?: number,
): Promise<ChatThreadResponse> {
  const params = new URLSearchParams({ contact_id: contactId });
  if (anchorId != null) params.set('anchor_id', String(anchorId));
  const response = await apiFetch(`/api/v1/system/chat-history/thread?${params.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load conversation'));
  return response.json();
}

/** Queues a CSV build into My Downloads; resolves as soon as the job is accepted. */
export async function exportChatHistory(filters: ChatHistoryFilters): Promise<{ id: string }> {
  const response = await apiFetch('/api/v1/system/chat-history/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(filters),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to queue export'));
  return response.json();
}
