/**
 * Turn trace service (S2b). Phase 2: these are the real endpoints.
 *
 * =============================================================================
 * THE BACKEND CONTRACT (implemented, `app/api/v1/system/chatbot.py`)
 * =============================================================================
 *
 * GET /api/v1/system/chatbot/turns
 *     ?contact_respond_id=&from=&to=&status=&limit=&cursor=
 *   Permission: `system.chat_history.view`. Newest first, keyset-paged.
 *   `limit` defaults to 50, max 200. `cursor` is the opaque `next_cursor` of the
 *   previous page; `next_cursor` is null on the last page. An unknown `status` is
 *   422, not an empty page.
 *   200 ->
 *   {
 *     "items": [
 *       {
 *         "id": "<uuid>",
 *         "contact_respond_id": "900000009",
 *         "message_id": "wamid.xxx" | null,
 *         "ingress": "webhook" | "poller" | "retry" | "console",
 *         "status": "queued" | "processing" | "delegated" | "done" | "failed",
 *         "stage": "received" | "understood" | "access" | "routed" | "looked_up"
 *                | "replied" | "remembered" | "sent" | "intake" | "queued"
 *                | "casual_llm" | null,
 *         "branch_kind": "business_query" | "out_of_scope" | ... | null,
 *         "error": "<one sentence>" | null,
 *         "attempt": 1,
 *         "is_test": false,
 *         "created_at": "<iso8601>",
 *         "started_at": "<iso8601>" | null,
 *         "finished_at": "<iso8601>" | null,
 *         "retry_requested_at": "<iso8601>" | null,
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
 * GET /api/v1/system/chatbot/turns/failed-contacts?from=&to=
 *   Permission: `system.chat_history.view`. Feeds the LIST's "Failed turns only"
 *   filter (AC-255). An aggregate, not a page of turns: the question is "which
 *   contacts are worth opening", which is tens of rows, and grouping every turn in
 *   the browser would be both expensive and wrong across a page boundary.
 *   200 -> { "items": [{ contact_respond_id, last_failed_stage, last_failed_at, count }] }
 *
 * POST /api/v1/system/chatbot/turns/{id}/retry
 *   Permission: `system.chat_history.manage` (403 without it).
 *   409 unless the turn is `failed` (R4: manual retry is the ONLY retry).
 *   409 `{code: "retry_unavailable"}` when the environment has no ingress configured,
 *       having sent nothing.
 *   409 when a retry for this turn is already in flight (`retry_requested_at` set),
 *       so a double click cannot answer the customer twice.
 *   502 when the ingress refuses; the row is left unchanged.
 *   200 -> { "turn_id": "<uuid>", "attempt": 2 }   // what the RE-INJECTED turn carries
 *
 * GET /api/v1/system/chatbot/retry-availability
 *   Permission: `system.chat_history.view`.
 *   200 -> { "available": boolean, "reason": "<sentence>" | null }
 *   Read so the UI can DISABLE Retry with the reason rather than offer a button that
 *   always 409s - one teaches an operator to distrust the screen, the other tells them
 *   it is an environment thing.
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
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ChatbotTurn,
  ChatbotTurnFilters,
  ChatbotTurnListResponse,
  FailedContactListResponse,
  FailedContactFilters,
  RetryAvailability,
  RetryTurnResponse,
} from '../types/chatbotTurn.types';

function buildParams(entries: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  Object.entries(entries).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    params.set(key, String(value));
  });
  return params.toString();
}

export async function getChatbotTurns(
  filters: ChatbotTurnFilters = {},
): Promise<ChatbotTurnListResponse> {
  const query = buildParams({
    contact_respond_id: filters.contact_respond_id,
    from: filters.from,
    to: filters.to,
    status: filters.status,
    limit: filters.limit,
    cursor: filters.cursor,
  });
  const response = await apiFetch(`/api/v1/system/chatbot/turns?${query}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load turns'));
  return response.json();
}

/** AC-255: which contacts have a failed turn in the range, and what stopped last. */
export async function getFailedChatbotContacts(
  filters: FailedContactFilters = {},
): Promise<FailedContactListResponse> {
  const query = buildParams({ from: filters.from, to: filters.to });
  const response = await apiFetch(`/api/v1/system/chatbot/turns/failed-contacts?${query}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load contacts with failed turns'));
  }
  return response.json();
}

export async function retryChatbotTurn(turnId: string): Promise<RetryTurnResponse> {
  const response = await apiFetch(`/api/v1/system/chatbot/turns/${turnId}/retry`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to retry turn'));
  return response.json();
}

/** Whether Retry can work in this environment at all, so the button can say so. */
export async function getRetryAvailability(): Promise<RetryAvailability> {
  const response = await apiFetch('/api/v1/system/chatbot/retry-availability');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to check retry availability'));
  }
  return response.json();
}

/** Index the turns of one contact by the respond message id each one answers. */
export function indexTurnsByMessageId(turns: ChatbotTurn[]): Map<string, ChatbotTurn> {
  const byMessage = new Map<string, ChatbotTurn>();
  for (const turn of turns) {
    if (!turn.message_id) continue;
    // The endpoint returns newest first and a retry is a SECOND row for the same message
    // (attempt 2). The newest is the one the operator wants: it is what the customer last
    // got, and it is the one whose Retry is live.
    if (!byMessage.has(turn.message_id)) byMessage.set(turn.message_id, turn);
  }
  return byMessage;
}
