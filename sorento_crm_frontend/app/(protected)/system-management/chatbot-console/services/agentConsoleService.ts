/**
 * The console's Agent tab backend (`app/api/v1/system/chatbot.py`, AGENTIC-P1).
 *
 * POST /api/v1/system/chatbot/agent/turn               { contact_respond_id, text } -> AgentTurnResponse
 *   409 { detail: { code: "agent_refused", reason } } when the contact may not use the agent.
 * GET  /api/v1/system/chatbot/agent/conversation?contact_respond_id=  -> AgentConversationResponse
 * POST /api/v1/system/chatbot/agent/conversation/new   { contact_respond_id } -> { conversation_id }
 *
 * All three need `system.chat_history.view`, like `/console/turn`.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import {
  AGENT_REFUSAL_MESSAGES,
  type AgentConversationResponse,
  type AgentTurnResponse,
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

async function refusalReason(response: Response): Promise<string | null> {
  try {
    const body = await response.clone().json();
    const detail = body?.detail;
    if (detail && detail.code === 'agent_refused' && typeof detail.reason === 'string') {
      return detail.reason;
    }
  } catch {
    // Not JSON: fall through to the generic error.
  }
  return null;
}

export async function postAgentTurn(contactRespondId: string, text: string): Promise<AgentTurnResponse> {
  const response = await apiFetch(`${BASE}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contact_respond_id: contactRespondId, text }),
  });
  if (!response.ok) {
    if (response.status === 409) {
      const reason = await refusalReason(response);
      if (reason) throw new AgentRefusedError(reason);
    }
    throw new Error(await extractApiError(response, 'The agent could not run this turn'));
  }
  return response.json();
}

export async function getAgentConversation(contactRespondId: string): Promise<AgentConversationResponse> {
  const params = new URLSearchParams({ contact_respond_id: contactRespondId });
  const response = await apiFetch(`${BASE}/conversation?${params.toString()}`);
  if (!response.ok) {
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
    throw new Error(await extractApiError(response, 'Failed to start a new conversation'));
  }
  return response.json();
}
