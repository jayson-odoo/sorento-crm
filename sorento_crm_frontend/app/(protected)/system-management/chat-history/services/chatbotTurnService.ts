/**
 * Turn trace service (S2b). Phase 2: these are the real endpoints.
 *
 * =============================================================================
 * THE BACKEND CONTRACT (implemented, `app/api/v1/system/chatbot.py`)
 * =============================================================================
 *
 * GET /api/v1/system/chatbot/turns
 *     ?contact_respond_id=&from=&to=&status=&ingress=&limit=&cursor=
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
 *     "next_cursor": "<opaque>" | null,
 *     "retry_available": true,
 *     "retry_unavailable_reason": "<sentence>" | null
 *   }
 *
 * ---------------------------------------------------------------------------
 * EXPECTED CONTRACT - the shadow window (L1-S4, AC-1027 / AC-1029 / AC-1030)
 * ---------------------------------------------------------------------------
 *
 * NOT IMPLEMENTED YET. Phase 1 builds the Shadow filter, the drift badge, the summary
 * line and the drawer's second parse column against the mock at the bottom of this file;
 * Phase 2 adds the endpoint half and the mock goes with this note.
 *
 * `ingress` joins the existing filters and takes one of
 * `webhook | poller | retry | console | shadow`. An unknown value is 422, the same as
 * `status`.
 *
 * EVERY row (live and shadow) gains one field:
 *
 *   "domains": ["inventory", "incoming"] | null
 *      the parse's `asks[]` flattened, in the order the dealer said them. `null` on a
 *      turn parsed before v3 - which is NOT `[]` ("named no domain"), because the drift
 *      comparison must not read "we cannot tell" as "these differ".
 *
 * A SHADOW row (`ingress: "shadow"`) also carries:
 *
 *   "shadow_of": "wamid.xxx"        the LIVE turn's `message_id`, which is what pairs
 *                                   the two sides. Null on every live row.
 *
 * and it carries no reply: `response` is null, nothing was sent, no session was written
 * and no escalation was raised. Its parse rides `trace` like any other turn's.
 *
 * `ingress=shadow` is ALSO valid with NO `contact_respond_id`: the owner watches a
 * promotion across every contact at once, not one conversation at a time. A row of such a
 * request carries its own context, because the screen showing it has no conversation open
 * to read it from:
 *
 *   "contact_display": "Ah Seng Hardware" | null    the contact's name, else the phone.
 *                                                   NEVER an id - the grid shows it.
 *   "message": "SRTWT2634 stock and eta" | null     what the customer said.
 *   "live": { "id": "<live turn uuid>",             the live side of the comparison, off
 *             "branch_kind": "business_query",      the join the summary already needs.
 *             "domains": ["inventory"] } | null     `id` is the LIVE turn, so opening a
 *                                                   row opens what the customer got.
 *
 * Those three are absent on a per-contact request, where the conversation already
 * supplies them.
 *
 * With `ingress=shadow` the response gains a summary over the WHOLE filtered range, not
 * over the page:
 *
 *   "summary": { "count": 42, "branch_parity": 0.97, "asks_parity": 0.91 } | null
 *
 * Parities are fractions of the shadow rows that could be paired with a live row, and
 * either may be null when nothing in the range could be compared. `null` for the whole
 * object when the filter was not `shadow`. It is computed server-side because the browser
 * holds one page and the owner is asking about the window.
 *
 * GET /api/v1/system/chatbot/turns/failed-contacts?from=&to=
 *   Permission: `system.chat_history.view`. Feeds the LIST's "Failed turns only"
 *   filter (AC-255): the contacts it names are sent back to
 *   `GET /api/v1/system/chat-history` as repeated `contact_id`, so the page, the total
 *   and the pager all describe the filtered set. A range is required and defaults to the
 *   last 7 days; the roster is capped at 200 contacts. An aggregate, not a page of turns: the question is "which
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
 * Whether Retry works in this environment at all rides the LIST response
 * (`retry_available`, `retry_unavailable_reason`), so the UI can DISABLE the button with
 * the reason rather than offer one that always 409s. It is one boolean the screen needs at
 * the same moment it needs the turns, which is why it is not a route of its own.
 *
 * GET /api/v1/system/chatbot/turns/{id}
 *   Permission: `system.chat_history.view`. The row above plus a normalised
 *   `trace_detail` (chatbot growth r1, Slice D): `{stages, parse, decay,
 *   open_question, focus, tool, crossdomain, reveals, session}`. Kinds no lane
 *   has written yet (`tool`, `crossdomain`, `reveals`, `decay`, `focus`,
 *   `open_question`) come back `null` / `[]`, never an error - the drawer
 *   renders an empty section for them. `stages` sorts the FAILING stage first
 *   on a failed turn. 404 for an unknown id.
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
  BranchKind,
  ChatbotTurn,
  ChatbotTurnDetail,
  ChatbotTurnFilters,
  ChatbotTurnListResponse,
  FailedContactListResponse,
  FailedContactFilters,
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
    ingress: filters.ingress,
    limit: filters.limit,
    cursor: filters.cursor,
  });
  // PHASE 1 MOCK: nothing serves `ingress=shadow` yet, and asking the real endpoint for
  // it would 422 rather than show the screen. Delete this branch, and `mockShadowTurns`
  // with it, when the endpoint lands.
  if (filters.ingress === 'shadow') return mockShadowTurns(filters);
  const response = await apiFetch(`/api/v1/system/chatbot/turns?${query}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load turns'));
  const body: ChatbotTurnListResponse = await response.json();
  rememberLiveTurns(filters.contact_respond_id, body.items);
  return body;
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

/** One turn's row plus its normalised `trace_detail` (Slice D, AC-970). */
export async function getChatbotTurn(turnId: string): Promise<ChatbotTurnDetail> {
  // PHASE 1 MOCK: the cross-contact grid's rows are a fixture, so their ids answer from
  // the fixture too - otherwise opening one would 404 and the drawer's two parse columns
  // could never be seen. Goes with the rest of the mock.
  if (turnId.startsWith('live-mock-') || turnId.startsWith('shadow-mock-')) {
    return mockTurnDetail(turnId);
  }
  const response = await apiFetch(`/api/v1/system/chatbot/turns/${turnId}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load turn detail'));
  return response.json();
}

export async function retryChatbotTurn(turnId: string): Promise<RetryTurnResponse> {
  const response = await apiFetch(`/api/v1/system/chatbot/turns/${turnId}/retry`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to retry turn'));
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

// ---------------------------------------------------------------------------
// PHASE 1 MOCK - the shadow window. DEBT, not done.
// ---------------------------------------------------------------------------
// Everything below exists so the Shadow filter, the drift badge and the summary line can
// be tuned with no backend, and it goes in one delete when the endpoint lands (with the
// `filters.ingress === 'shadow'` branch above and the EXPECTED CONTRACT note at the top).
//
// It shadows the REAL turns the contact already has rather than inventing message ids,
// because the pairing is the whole feature: a shadow row nothing can be compared with
// would make the badge and the parities untestable. So the live answer is remembered as
// it goes past, and the shadow rows are derived from it.
//
// The three states the screen owes, and how to reach each one:
//
// per-contact (the conversation drawer):
//   success - a contact with turns; every 3rd row drifts on branch, every 5th on domains
//   empty   - a contact whose turns have not been loaded, or who has none
//   error   - a contact whose respond id ends in 9 (a stand-in for the endpoint failing)
//
// cross-contact (the chat-history grid), which has no live turns to shadow because that
// page lists MESSAGES, so it gets a fixture instead:
//   success - the default range
//   empty   - a range that starts in the future
//   error   - an inverted range (`from` after `to`)
// Both levers are reachable from the two date inputs the page already has, so every state
// can be seen in a browser without editing code.
const mockLiveTurns = new Map<string, ChatbotTurn[]>();

function rememberLiveTurns(contactId: string | undefined, items: ChatbotTurn[]): void {
  if (contactId) mockLiveTurns.set(contactId, items);
}

const MOCK_BRANCH_DRIFT: BranchKind = 'clarify_menu';

const MOCK_CROSS_CONTACT_ROWS: {
  contact: string;
  message: string;
  live: BranchKind;
  liveDomains: string[];
  shadow: BranchKind;
  shadowDomains: string[];
}[] = [
  {
    contact: 'Ah Seng Hardware',
    message: 'SRTWT2634 stock and eta',
    live: 'business_query',
    liveDomains: ['inventory'],
    shadow: 'business_query',
    shadowDomains: ['inventory', 'incoming'],
  },
  {
    contact: 'Ah Seng Hardware',
    message: 'PO?',
    live: 'business_query',
    liveDomains: ['inventory'],
    shadow: 'business_query',
    shadowDomains: ['purchase_order'],
  },
  {
    contact: 'Hanlim Trading',
    message: 'delivery to hanlim',
    live: 'clarify_menu',
    liveDomains: [],
    shadow: 'business_query',
    shadowDomains: ['order'],
  },
  {
    contact: 'Hanlim Trading',
    message: 'thanks bro',
    live: 'out_of_scope',
    liveDomains: [],
    shadow: 'out_of_scope',
    shadowDomains: [],
  },
  {
    contact: 'Mocha Bathroom Gallery',
    message: 'promo for CWCX7605',
    live: 'check_promotion',
    liveDomains: ['promotion'],
    shadow: 'check_promotion',
    shadowDomains: ['promotion'],
  },
  {
    contact: 'Mocha Bathroom Gallery',
    message: '1',
    live: 'business_query',
    liveDomains: ['inventory'],
    shadow: 'low_signal',
    shadowDomains: ['inventory'],
  },
  {
    contact: 'Sim Trading (Klang)',
    message: 'last in for SRTWC8517',
    live: 'business_query',
    liveDomains: ['spo_allocation'],
    shadow: 'business_query',
    shadowDomains: ['spo_allocation'],
  },
];

function mockCrossContactShadowTurns(
  filters: ChatbotTurnFilters,
): Promise<ChatbotTurnListResponse> {
  const from = filters.from ? new Date(filters.from) : null;
  const to = filters.to ? new Date(filters.to) : null;
  if (from && to && from > to) {
    return Promise.reject(new Error('Shadow turns could not be loaded'));
  }
  const empty = Boolean(from && from.getTime() > Date.now());
  const rows = empty ? [] : MOCK_CROSS_CONTACT_ROWS;
  const items: ChatbotTurn[] = rows.map((row, index) => ({
    id: `shadow-mock-${index}`,
    contact_respond_id: `9000000${index}`,
    message_id: `wamid.mock-${index}`,
    status: 'done',
    stage: 'sent',
    branch_kind: row.shadow,
    attempt: 1,
    is_test: false,
    ingress: 'shadow',
    created_at: new Date(Date.now() - (index + 1) * 900_000).toISOString(),
    finished_at: new Date(Date.now() - (index + 1) * 900_000).toISOString(),
    trace: [],
    response: null,
    shadow_of: `wamid.mock-${index}`,
    domains: row.shadowDomains,
    contact_display: row.contact,
    message: row.message,
    live: { id: `live-mock-${index}`, branch_kind: row.live, domains: row.liveDomains },
  }));
  const drifted = items.filter((item) => item.live?.branch_kind !== item.branch_kind).length;
  const asksDrifted = items.filter(
    (item) => (item.live?.domains ?? []).join(',') !== (item.domains ?? []).join(','),
  ).length;
  return Promise.resolve({
    items,
    next_cursor: null,
    summary: items.length
      ? {
          count: items.length,
          branch_parity: (items.length - drifted) / items.length,
          asks_parity: (items.length - asksDrifted) / items.length,
        }
      : null,
  });
}

function mockShadowTurns(filters: ChatbotTurnFilters): Promise<ChatbotTurnListResponse> {
  if (!filters.contact_respond_id) return mockCrossContactShadowTurns(filters);
  const contactId = filters.contact_respond_id ?? '';
  if (contactId.endsWith('9')) {
    return Promise.reject(new Error('Shadow turns could not be loaded'));
  }
  const live = mockLiveTurns.get(contactId) ?? [];
  const items: ChatbotTurn[] = live
    .filter((turn) => Boolean(turn.message_id))
    .map((turn, index) => {
      const branchDrift = index % 3 === 0;
      const domainDrift = index % 5 === 0;
      const domains = turn.domains ?? ['inventory'];
      return {
        ...turn,
        id: `shadow-${turn.id}`,
        ingress: 'shadow' as const,
        shadow_of: turn.message_id,
        branch_kind: branchDrift ? MOCK_BRANCH_DRIFT : turn.branch_kind,
        domains: domainDrift ? [...domains].reverse().concat('purchase_order') : domains,
        response: null,
      };
    });
  const paired = items.length;
  const drifted = items.filter((_, index) => index % 3 === 0).length;
  const asksDrifted = items.filter((_, index) => index % 5 === 0).length;
  return Promise.resolve({
    items,
    next_cursor: null,
    summary: paired
      ? {
          count: paired,
          branch_parity: (paired - drifted) / paired,
          asks_parity: (paired - asksDrifted) / paired,
        }
      : null,
  });
}

function mockTurnDetail(turnId: string): Promise<ChatbotTurnDetail> {
  const isShadow = turnId.startsWith('shadow-mock-');
  const index = Number(turnId.replace(/^(live|shadow)-mock-/, '')) || 0;
  const row = MOCK_CROSS_CONTACT_ROWS[index] ?? MOCK_CROSS_CONTACT_ROWS[0];
  const domains = isShadow ? row.shadowDomains : row.liveDomains;
  return Promise.resolve({
    id: turnId,
    contact_respond_id: `9000000${index}`,
    message_id: `wamid.mock-${index}`,
    status: 'done',
    stage: 'sent',
    branch_kind: isShadow ? row.shadow : row.live,
    attempt: 1,
    is_test: false,
    ingress: isShadow ? 'shadow' : 'webhook',
    created_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    trace: [],
    response: null,
    domains,
    trace_detail: {
      stages: [],
      parse: {
        raw: { message_type: 'business_query', asks: domains.map((domain) => ({ domain, entities: [] })) },
        post_processed: { branch_kind: isShadow ? row.shadow : row.live, domains },
        prompt_version: isShadow ? 'v19' : 'v18',
        model: 'gpt-4.1-mini',
      },
      decay: [],
      open_question: null,
      focus: [],
      tool: null,
      crossdomain: [],
      reveals: { restricted_fields_seen: [], granted: [], dropped: [] },
      session: { before: {}, after: {}, diff: [] },
    },
  });
}
