/**
 * The console's Auto tab backend (`app/api/v1/system/chatbot.py`, AGENTIC-P2).
 *
 * POST /api/v1/system/chatbot/console/auto-turn { contact_respond_id, text, session_vars, run_id }
 *   -> { route, turn }: `turn` is a console turn when route is `chat`, an agent turn when `agent`.
 *   409 { detail: { code: "agent_busy" } } while the agent is still working for the contact.
 *
 * Needs `system.chat_history.view`, like `/console/turn`.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { AgentRefusedError, refusalReason } from './agentConsoleService';
import type { AgentTurnResponse, AutoRoute } from '../types/agentConsole.types';

export interface AutoTurnRequest {
  contact_respond_id: string;
  text: string;
  session_vars: Record<string, unknown> | null;
  run_id: string;
}

/** The bot side of an Auto reply: the fields of a console turn the tab shows. */
export interface AutoBotTurn {
  turn_id: string | null;
  branch_kind?: string | null;
  reply_text: string;
  quick_replies?: string[];
  send_messages?: string[];
  session_vars?: Record<string, unknown> | null;
}

export interface AutoTurnResponse {
  route: AutoRoute;
  turn: AutoBotTurn | AgentTurnResponse;
}

export async function postAutoTurn(body: AutoTurnRequest): Promise<AutoTurnResponse> {
  const response = await apiFetch('/api/v1/system/chatbot/console/auto-turn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 409) {
      const reason = await refusalReason(response);
      if (reason) throw new AgentRefusedError(reason);
    }
    throw new Error(await extractApiError(response, 'The message could not be sent'));
  }
  return response.json();
}
