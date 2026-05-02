import { apiFetch } from '@/lib/api';
import type { AIPageSnapshot } from '@/lib/aiPageSnapshot';

export type { AIPageSnapshot };

export interface AIAssistantMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  metadata_json: {
    links?: string[];
    sources?: Array<{ title?: string }>;
    selected_tools?: Array<{ tool_name?: string }>;
    suggestions?: string[];
  };
  created_at: string;
}

export interface AIAssistantConversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: AIAssistantMessage[];
}

export interface AIAssistantConversationSummary {
  id: string;
  title: string | null;
  updated_at: string;
}

export interface AIAssistantConversationList {
  items: AIAssistantConversationSummary[];
}

export interface AIAssistantGreeting {
  greeting: string;
  suggestions: string[];
}

export async function fetchAIAssistantGreeting(): Promise<AIAssistantGreeting> {
  const r = await apiFetch('/api/v1/system/ai-assistant/greeting', { method: 'GET' });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to load greeting');
  }
  return (await r.json()) as AIAssistantGreeting;
}

export async function sendAIAssistantMessage(
  message: string,
  conversationId?: string,
  pageSnapshot?: AIPageSnapshot | null,
) {
  const r = await apiFetch('/api/v1/system/ai-assistant/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
      page_snapshot: pageSnapshot ?? null,
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to chat with AI assistant');
  }
  return (await r.json()) as AIAssistantConversation;
}

export async function listAIAssistantConversations(params: { q?: string; limit?: number } = {}) {
  const search = new URLSearchParams();
  if (params.q && params.q.trim().length > 0) search.set('q', params.q.trim());
  if (typeof params.limit === 'number') search.set('limit', String(params.limit));
  const qs = search.toString();
  const url = `/api/v1/system/ai-assistant/conversations${qs ? `?${qs}` : ''}`;
  const r = await apiFetch(url, { method: 'GET' });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to load conversations');
  }
  const data = await r.json();
  if (Array.isArray(data)) return { items: data as AIAssistantConversationSummary[] };
  return data as AIAssistantConversationList;
}

export async function loadConversation(id: string) {
  const r = await apiFetch(`/api/v1/system/ai-assistant/conversations/${id}/messages`, {
    method: 'GET',
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to load conversation');
  }
  const data = await r.json();
  if (Array.isArray(data)) {
    return {
      id,
      title: null,
      created_at: '',
      updated_at: '',
      messages: data as AIAssistantMessage[],
    } as AIAssistantConversation;
  }
  return data as AIAssistantConversation;
}
