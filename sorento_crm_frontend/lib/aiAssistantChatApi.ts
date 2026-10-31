import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { AIPageSnapshot } from '@/lib/aiPageSnapshot';
import type { TurnAttachment } from '@/components/chatbot/TurnAttachments';
import {
  ActionRefusedError,
  actionRefusalReason,
} from '@/app/(protected)/system-management/chatbot-console/services/agentConsoleService';
import type {
  AgentActionResponse,
  AgentConversationAction,
  AgentPendingAction,
  AgentReplyMeta,
  AgentSteps,
} from '@/app/(protected)/system-management/chatbot-console/types/agentConsole.types';
import type { ConsoleRoute } from '@/app/(protected)/system-management/chatbot-console/types/chatbotConsole.types';

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
    // M3a Clarifier: enumerable options rendered as clickable chips; a click
    // sends the option text as the next turn.
    clarify?: { options?: string[] };
    // M3a Write-confirm: a pending write awaiting explicit Confirm/Cancel. Only
    // status === 'pending' renders the buttons; confirmed/cancelled/denied/failed
    // are terminal (buttons hidden).
    pending_confirmation?: {
      tool_name?: string;
      status?: 'pending' | 'confirmed' | 'cancelled' | 'denied' | 'failed';
      summary?: string;
    };
    // The chatbot's brain answered (AGENTIC-UNIFY): `route` is present only on its replies and picks
    // the renderer. The server strips everything but `route`, `status`, files, chips and the card
    // (`agent.pending_action`, `agent.actions`) for a reader without the settings view slug.
    route?: 'chat' | 'agent';
    status?: string | null;
    chatbot_turn_id?: string | null;
    route_decision?: ConsoleRoute | null;
    attachments?: TurnAttachment[];
    agent?: {
      pending_action?: AgentPendingAction | null;
      actions?: AgentConversationAction[];
      rounds?: number | null;
      tool_calls?: { name: string; status: string }[];
      limit_hit?: AgentReplyMeta['limit_hit'];
      steps?: AgentSteps;
    } | null;
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
  confirmAction?: 'confirm' | 'cancel',
) {
  const r = await apiFetch('/api/v1/system/ai-assistant/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || null,
      page_snapshot: pageSnapshot ?? null,
      confirm_action: confirmAction ?? null,
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

const ACTIONS = '/api/v1/system/ai-assistant/agent/actions';

async function decidePanelAction(path: string, fallback: string): Promise<AgentActionResponse> {
  const r = await apiFetch(`${ACTIONS}/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!r.ok) {
    if (r.status === 409) {
      const reason = await actionRefusalReason(r);
      if (reason) throw new ActionRefusedError(reason);
    }
    throw new Error(await extractApiError(r, fallback));
  }
  return (await r.json()) as AgentActionResponse;
}

export function confirmPanelAction(actionId: string) {
  return decidePanelAction(`${encodeURIComponent(actionId)}/confirm`, 'Failed to confirm the changes');
}

export function cancelPanelAction(actionId: string) {
  return decidePanelAction(`${encodeURIComponent(actionId)}/cancel`, 'Failed to cancel the changes');
}

export function withdrawPanelStep(actionId: string, index: number) {
  return decidePanelAction(
    `${encodeURIComponent(actionId)}/steps/${index}/withdraw`,
    'Failed to withdraw the change',
  );
}
