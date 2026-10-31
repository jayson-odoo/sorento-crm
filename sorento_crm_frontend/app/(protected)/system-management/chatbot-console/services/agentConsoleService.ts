/**
 * The agent's own routes behind the console thread (`app/api/v1/system/chatbot.py`).
 *
 * GET  /api/v1/system/chatbot/agent/conversation?contact_respond_id=  -> AgentConversationResponse
 * The console thread and every turn go through `chatbotConsoleService`.
 * POST /api/v1/system/chatbot/agent/conversation/new   { contact_respond_id } -> { conversation_id }
 * POST /api/v1/system/chatbot/agent/actions/{id}/confirm { contact_respond_id } -> AgentActionResponse
 * POST /api/v1/system/chatbot/agent/actions/{id}/cancel  { contact_respond_id } -> AgentActionResponse
 * POST /api/v1/system/chatbot/agent/actions/{id}/steps/{n}/withdraw { contact_respond_id } -> AgentActionResponse
 *   409 { detail: { code: "action_refused", reason } } when the proposal can no longer be decided.
 *
 * All of them need `system.chat_history.view`, like `/console/turn`.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  ACTION_REFUSAL_MESSAGES,
  AGENT_REFUSAL_MESSAGES,
  type AgentActionResponse,
  type AgentConversationResponse,
} from '../types/agentConsole.types';

const BASE = '/api/v1/system/chatbot/agent';

/** The agent refused this contact; `message` is plain words for the thread. */
export class AgentRefusedError extends Error {
  reason: string;

  constructor(reason: string) {
    super(AGENT_REFUSAL_MESSAGES[reason] ?? 'The agent cannot run for this contact.');
    this.name = 'AgentRefusedError';
    this.reason = reason;
  }
}

/** The proposal can no longer be confirmed or cancelled; `message` is plain words. */
export class ActionRefusedError extends Error {
  reason: string;

  constructor(reason: string) {
    super(ACTION_REFUSAL_MESSAGES[reason] ?? 'This proposal can no longer be decided.');
    this.name = 'ActionRefusedError';
    this.reason = reason;
  }
}

async function actionRefusalReason(response: Response): Promise<string | null> {
  try {
    const detail = (await response.clone().json())?.detail;
    if (detail && detail.code === 'action_refused' && typeof detail.reason === 'string') {
      return detail.reason;
    }
  } catch {
    // Not JSON: fall through to the generic error.
  }
  return null;
}

async function decideAction(
  contactRespondId: string,
  actionId: string,
  decision: 'confirm' | 'cancel',
): Promise<AgentActionResponse> {
  const response = await apiFetch(`${BASE}/actions/${encodeURIComponent(actionId)}/${decision}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_respond_id: contactRespondId }),
  });
  if (!response.ok) {
    if (response.status === 409) {
      const reason = await actionRefusalReason(response);
      if (reason) throw new ActionRefusedError(reason);
    }
    throw new Error(
      await extractApiError(
        response,
        decision === 'confirm' ? 'Failed to confirm the changes' : 'Failed to cancel the changes',
      ),
    );
  }
  return response.json();
}

/** Withdraw a done step whose change still waits out its grace window (nothing applied, nobody told). */
export async function withdrawAgentStep(
  contactRespondId: string,
  actionId: string,
  index: number,
): Promise<AgentActionResponse> {
  const response = await apiFetch(
    `${BASE}/actions/${encodeURIComponent(actionId)}/steps/${index}/withdraw`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contact_respond_id: contactRespondId }),
    },
  );
  if (!response.ok) {
    if (response.status === 409) {
      const reason = await actionRefusalReason(response);
      if (reason) throw new ActionRefusedError(reason);
    }
    throw new Error(await extractApiError(response, 'Failed to withdraw the change'));
  }
  return response.json();
}

export function confirmAgentAction(contactRespondId: string, actionId: string) {
  return decideAction(contactRespondId, actionId, 'confirm');
}

export function cancelAgentAction(contactRespondId: string, actionId: string) {
  return decideAction(contactRespondId, actionId, 'cancel');
}

async function refusalReason(response: Response): Promise<string | null> {
  try {
    const body = await response.clone().json();
    const detail = body?.detail;
    if (detail && detail.code === 'agent_refused' && typeof detail.reason === 'string') {
      return detail.reason;
    }
    if (detail && detail.code === 'agent_busy') return 'agent_busy';
  } catch {
    // Not JSON: fall through to the generic error.
  }
  return null;
}

export async function getAgentConversation(contactRespondId: string): Promise<AgentConversationResponse> {
  const params = new URLSearchParams({ contact_respond_id: contactRespondId });
  const response = await apiFetch(`${BASE}/conversation?${params.toString()}`);
  if (!response.ok) {
    if (response.status === 409) {
      const reason = await refusalReason(response);
      if (reason) throw new AgentRefusedError(reason);
    }
    throw new Error(await extractApiError(response, 'Failed to load the conversation'));
  }
  return response.json();
}

export async function newAgentConversation(contactRespondId: string): Promise<{ conversation_id: string }> {
  const response = await apiFetch(`${BASE}/conversation/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_respond_id: contactRespondId }),
  });
  if (!response.ok) {
    if (response.status === 409) {
      const reason = await refusalReason(response);
      if (reason) throw new AgentRefusedError(reason);
    }
    throw new Error(await extractApiError(response, 'Failed to start a new conversation'));
  }
  return response.json();
}
