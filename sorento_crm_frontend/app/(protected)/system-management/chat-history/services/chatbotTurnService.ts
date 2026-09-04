/**
 * Turn trace service (S2b). **PHASE 1: THIS RETURNS MOCK DATA.**
 *
 * =============================================================================
 * THE BACKEND CONTRACT THIS IS BUILT AGAINST (Phase 2 implements it, AC-257)
 * =============================================================================
 *
 * GET /api/v1/system/chatbot/turns?contact_respond_id=&from=&to=&status=
 *   Permission: `system.chat_history.view`. Newest first, paged.
 *   200 ->
 *   {
 *     "items": [
 *       {
 *         "id": "<uuid>",
 *         "contact_respond_id": "900000009",
 *         "message_id": "wamid.xxx" | null,
 *         "status": "queued" | "processing" | "delegated" | "done" | "failed",
 *         "stage": "received" | "understood" | "access" | "routed" | "looked_up"
 *                | "replied" | "remembered" | "sent" | "intake" | "queued"
 *                | "casual_llm" | null,
 *         "branch_kind": "business_query" | "out_of_scope" | ... | null,
 *         "attempt": 1,
 *         "is_test": false,
 *         "created_at": "<iso8601>",
 *         "finished_at": "<iso8601>" | null,
 *         "trace": [
 *           {
 *             "stage": "understood",
 *             "status": "ok" | "failed" | "skipped",
 *             "started_at": "<iso8601>",
 *             "ms": 2310,
 *             "summary": "<one sentence, plain language>",
 *             "why": "<one sentence, plain language>",
 *             "facts": { "<label>": "<scalar>" },
 *             "error": "<one sentence>" | null,
 *             "raw": { ...technical payload, byte-capped by the engine... }
 *           }
 *         ],
 *         "response": { "ctx": {...}, "item": {...}, "actions": [...] } | null
 *       }
 *     ],
 *     "next_cursor": "<opaque>" | null
 *   }
 *
 * POST /api/v1/system/chatbot/turns/{id}/retry
 *   Permission: `system.chat_history.manage`. 403 without it; 409 unless the turn is
 *   `failed` (R4: manual retry is the ONLY retry, and only from a failed turn).
 *   200 -> { "turn_id": "<uuid>", "attempt": 2 }
 *
 * Two properties the UI depends on and the endpoint owes:
 *
 * - `summary` and `why` are sentences the ENGINE composed from structured state (D11).
 *   The screen renders them verbatim. It must never be asked to build prose out of
 *   `facts`, because that would put the wording back in the frontend where nobody
 *   reviews it against what the turn actually did.
 * - `trace` is ordered and may be SHORT. A lane that never looks anything up has no
 *   `looked_up` record at all; a turn that failed at `understood` has nothing after it.
 *   The timeline renders what is there and collapses the rest into one "not reached" row,
 *   rather than inventing greyed placeholders for stages that were never going to run.
 *
 * =============================================================================
 * Swapping the mock out is a one-line change per function: delete the
 * `MOCK_*` return and uncomment the `apiFetch` call. Nothing above this layer
 * knows the difference - that is the point of the seam.
 * =============================================================================
 */
import type {
  ChatbotTurn,
  ChatbotTurnFilters,
  ChatbotTurnListResponse,
  RetryTurnResponse,
} from '../types/chatbotTurn.types';
import { MOCK_TURNS } from './chatbotTurn.mock';

/** Phase 1 only. Long enough to see the skeleton, short enough not to annoy. */
const MOCK_LATENCY_MS = 350;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), MOCK_LATENCY_MS));
}

export async function getChatbotTurns(
  filters: ChatbotTurnFilters = {},
): Promise<ChatbotTurnListResponse> {
  // --- PHASE 2 -------------------------------------------------------------
  // const params = buildDataGridParams({}, {
  //   contact_respond_id: filters.contact_respond_id,
  //   from: filters.from,
  //   to: filters.to,
  //   status: filters.status,
  // });
  // const response = await apiFetch(`/api/v1/system/chatbot/turns?${params}`);
  // if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load turns'));
  // return response.json();
  // -------------------------------------------------------------------------
  // PHASE 1: `contact_respond_id` is deliberately NOT applied. The fixture is a set of
  // SHAPES to review, not a store, and keying it to one invented contact would leave the
  // screen blank on every real thread in the dev database - which reads as a broken
  // feature rather than as an unfinished one. `status` IS applied, because the filter it
  // drives is part of what Phase 1 has to demonstrate.
  const items = MOCK_TURNS.filter(
    (turn) => !filters.status || turn.status === filters.status,
  );
  return delay({ items, next_cursor: null });
}

export async function retryChatbotTurn(turnId: string): Promise<RetryTurnResponse> {
  // --- PHASE 2 -------------------------------------------------------------
  // const response = await apiFetch(`/api/v1/system/chatbot/turns/${turnId}/retry`, {
  //   method: 'POST',
  // });
  // if (!response.ok) throw new Error(await extractApiError(response, 'Failed to retry turn'));
  // return response.json();
  // -------------------------------------------------------------------------
  const turn = MOCK_TURNS.find((t) => t.id === turnId);
  if (!turn) throw new Error('Turn not found');
  if (turn.status !== 'failed') throw new Error('Only a failed turn can be retried');
  return delay({ turn_id: turnId, attempt: turn.attempt + 1 });
}

/** Index the turns of one contact by the respond message id each one answers. */
export function indexTurnsByMessageId(turns: ChatbotTurn[]): Map<string, ChatbotTurn> {
  const byMessage = new Map<string, ChatbotTurn>();
  for (const turn of turns) {
    if (!turn.message_id) continue;
    // Oldest wins: a duplicate delivery is a second ROW for the same message, and the
    // first is the one that actually answered the customer.
    if (!byMessage.has(turn.message_id)) byMessage.set(turn.message_id, turn);
  }
  return byMessage;
}
