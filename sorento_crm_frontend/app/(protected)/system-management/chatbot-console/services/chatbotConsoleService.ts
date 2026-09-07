/**
 * The in-app chatbot console's own backend (Slice D final, chatbot growth r1).
 *
 * =============================================================================
 * THE BACKEND CONTRACT (`app/api/v1/system/chatbot.py`)
 * =============================================================================
 *
 * POST /api/v1/system/chatbot/console/turn
 *   Permission: `system.chat_history.view`. Runs one turn IN PROCESS, `is_test=True`,
 *   `ingress=console` (D14: nothing reaches a real customer, zero writes outside
 *   `chatbot.turns`).
 *   Body -> { contact_respond_id, text, session_vars: object|null, prompt_version_id:
 *             string|null, run_id, media?: {kind, filename, mime, content_base64}|null }
 *   200 ->
 *   {
 *     "turn_id": "<uuid>" | null,
 *     "branch_kind": "business_query" | "not_supported" | ... | null,
 *     "reply_text": "<string, may be empty>",
 *     "quick_replies": ["<chip text>", ...],
 *     "send_messages": ["<extra bot bubble text>", ...],
 *     "session_vars": {...} | null,
 *     "trace_summary": {
 *       "tool": "<mcp tool name>" | null,
 *       "args_short": {...} | null,
 *       "crossdomain_rungs": ["<rung>", ...],
 *       "reveals_dropped": ["<field key>", ...]
 *     }
 *   }
 *   404 `{code: "CHATBOT_CONSOLE_NO_ENVELOPE", ...}` - the contact has no prior chatbot
 *   turn to borrow a session shape from.
 *
 * GET /api/v1/system/chatbot/console/prompt-versions
 *   Permission: `system.chat_history.view`. `chatbot_semantic_parser` versions, newest
 *   first.
 *   200 -> [{ "id": "<uuid>", "version": 16, "label": "production" | null, "chars": 4211 }]
 *
 * GET /api/v1/system/chatbot/console/media/{media_id}   (commit 2)
 *   200 -> { "status": "pending" | "done" | "failed", "text": string | null,
 *            "error": string | null }
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ConsoleMediaStatusResponse,
  ConsolePromptVersion,
  ConsoleTurnRequest,
  ConsoleTurnResponse,
} from '../types/chatbotConsole.types';

const BASE = '/api/v1/system/chatbot/console';

export async function postConsoleTurn(body: ConsoleTurnRequest): Promise<ConsoleTurnResponse> {
  const response = await apiFetch(`${BASE}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to run the turn'));
  }
  return response.json();
}

export async function getConsolePromptVersions(): Promise<ConsolePromptVersion[]> {
  const response = await apiFetch(`${BASE}/prompt-versions`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load prompt versions'));
  }
  return response.json();
}

export async function getConsoleMediaStatus(mediaId: string): Promise<ConsoleMediaStatusResponse> {
  const response = await apiFetch(`${BASE}/media/${mediaId}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to check media status'));
  }
  return response.json();
}
