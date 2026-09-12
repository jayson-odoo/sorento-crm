/**
 * The turn trace shown under each incoming message in the Chat History drawer.
 *
 * Mirrors `chatbot.turns` (backend `app/models/chatbot_turn.py`). Field names follow the
 * wire, not frontend taste: a rename here is a contract break with the endpoint and with
 * the 1,535 captured fixtures the engine is graded against.
 */

/** The nine stages a turn can record, in the order the timeline renders them. */
export const TURN_STAGES = [
  'received',
  'understood',
  // L1-S3: did this message answer the question the bot was waiting for? Its outcome
  // decides the lane, so it is a row on the timeline and not a footnote.
  'answered',
  'access',
  'routed',
  'looked_up',
  'replied',
  'remembered',
  'sent',
] as const;
export type TurnStage = (typeof TURN_STAGES)[number];

/**
 * Where a turn stopped. A superset of `TurnStage`: four failure points sit outside the
 * timeline - `intake` is before the first trace record exists, `queued` is the per-contact
 * wait, `casual_llm` is the small-talk clarifier, and `delegated` is a turn an n8n lane
 * took over and never finished (the server's sweep fails it after the TTL).
 */
export type TurnFailureStage = TurnStage | 'intake' | 'queued' | 'casual_llm' | 'delegated';

export type TurnStatus = 'queued' | 'processing' | 'delegated' | 'done' | 'failed';

export type TraceStatus = 'ok' | 'failed' | 'skipped';

/** The 13 lanes the router decides between. */
export type BranchKind =
  | 'access_denied'
  | 'escalate_offer'
  | 'out_of_scope'
  | 'ideate'
  | 'offer_hold'
  | 'escalation_declined'
  | 'check_promotion'
  | 'low_signal'
  | 'clarify_menu'
  | 'not_supported'
  | 'stock_denied'
  | 'demand_qty'
  | 'business_query';

/**
 * One stage of one turn.
 *
 * `summary` and `why` are SENTENCES the engine composes from structured state - never from
 * the customer's text and never by an LLM (D11). The screen renders them as written; it
 * does not build prose of its own out of `facts`.
 */
/**
 * Everything in `trace` that is NOT a stage the turn ran.
 *
 * `note` is something that happened TO the turn - today, an operator asking for a retry;
 * it carries the stage the turn stopped at so the endpoint can file it with the failure.
 * The other six are sub-events a stage produced (`TurnTrace.add`, backend
 * `app/services/chatbot/trace.py`): one MCP tool call, one cross-domain rung probe, the
 * field reveals, and so on. They ride the SAME array as the stage records and carry no
 * `stage` at all, which is why the split below is on `kind` being absent and not on
 * `kind !== 'note'` - that read crashed the panel the first time a `tool` event landed.
 */
export type TurnTraceKind =
  | 'note'
  | 'tool'
  | 'crossdomain'
  | 'reveals'
  | 'decay'
  | 'focus'
  | 'open_question';

/**
 * One entry of `chatbot.turns.trace` - a stage record, a note, or a sub-event.
 *
 * Every field past `kind` is optional because a sub-event has none of them. Narrow to a
 * stage record with `stageRecords()` / `isStageRecord()` before reading `stage`.
 */
export interface TurnTraceRecord {
  /**
   * Absent on a stage record, present on everything else in the array that is NOT a step
   * the turn ran. `note` is something that happened TO the turn (an operator asking for a
   * retry); the rest are structured DECISIONS the engine took inside a stage - `decay`,
   * `focus`, `open_question`, `tool`, `crossdomain`, `reveals` - written by
   * `trace.TurnTrace.add`. None has a start, a duration or a status of its own, so none is
   * a timeline row.
   */
  kind?: TurnTraceKind;
  stage?: TurnStage;
  status?: TraceStatus;
  started_at?: string;
  ms?: number;
  summary?: string;
  why?: string;
  /** Small flat dict rendered as key/value rows under the sentences. */
  facts?: Record<string, unknown>;
  error?: string | null;
  /** Technical payload for the "Technical details" viewer. Byte-capped by the engine. */
  raw?: unknown;
  /** A sub-event spreads its own payload flat beside `kind`. */
  [extra: string]: unknown;
}

/** A record `TurnTrace.record` wrote: carries `stage`, never `kind`. The timeline rows. */
export interface TurnStageRecord extends TurnTraceRecord {
  kind?: undefined;
  stage: TurnStage;
  status: TraceStatus;
  started_at: string;
  ms: number;
  summary: string;
  why: string;
  facts: Record<string, unknown>;
  error: string | null;
}

/** The answer the turn returned. Null while the turn is still running, or when it failed. */
export interface TurnResponseBody {
  ctx?: Record<string, unknown> | null;
  item?: Record<string, unknown> | null;
  reply?: { text?: string | null; quick_replies?: unknown[] } | null;
  actions?: Record<string, unknown>[] | null;
}

/**
 * How the turn arrived. `shadow` (L1-S4, AC-1027) is the odd one: it is not a delivery at
 * all but a SECOND parse of a live turn, run under the version named by
 * `system_settings.chatbot_parser_shadow_version`. A shadow row sends nothing, writes no
 * session and escalates nothing; it exists to be compared with the live row it names in
 * `shadow_of`.
 */
export type TurnIngress = 'webhook' | 'poller' | 'retry' | 'console' | 'shadow';

export interface ChatbotTurn {
  id: string;
  contact_respond_id: string;
  /** The respond.io message id this turn answers. Null for a console-driven turn. */
  message_id: string | null;
  status: TurnStatus;
  /** Where it stopped. Null on a turn that is still running. */
  stage: TurnFailureStage | null;
  branch_kind: BranchKind | null;
  /** Manual retries from this screen. 1 on a turn nobody has retried. */
  attempt: number;
  is_test: boolean;
  // Optional, all four: the API always sends them, but nothing in the UI needs them to
  // be there. Requiring them would only force every caller that legitimately does not
  // have one - a test factory, a narrower projection, a response from before the column
  // existed - to invent a value, which is how a type stops describing reality.
  ingress?: TurnIngress;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at: string | null;
  /** Set while a requested retry is on its way; the row itself stays `failed`. */
  retry_requested_at?: string | null;
  trace: TurnTraceRecord[];
  response: TurnResponseBody | null;
  /**
   * AC-1027. On a shadow row, the `message_id` of the LIVE turn it parsed again. Null on
   * every live row, which is what pairs the two sides for the drift comparison.
   */
  shadow_of?: string | null;
  /**
   * AC-1029. The domains this turn's parse asked about, flattened from `asks[]` and kept
   * in the order the dealer said them. Null on a turn parsed before v3 - which is NOT the
   * same as `[]` ("this parse named no domain"), so the drift comparison treats an
   * unknown side as no drift rather than as a difference.
   */
  domains?: string[] | null;
  /**
   * AC-1029, the CROSS-CONTACT grid only. A shadow row asked for without a
   * `contact_respond_id` has to carry its own context, because the screen showing it has
   * no conversation open to read it from: who said it, what they said, and the live
   * answer to compare against. Absent on every row of a per-contact request.
   */
  contact_display?: string | null;
  message?: string | null;
  live?: ShadowTurnLiveSide | null;
}

/**
 * The live side of one shadow row, as the endpoint's own join already has it.
 *
 * `id` is the LIVE turn, so opening the row opens the turn the customer actually got,
 * with the shadow parse beside it rather than in place of it.
 */
export interface ShadowTurnLiveSide {
  id: string;
  branch_kind: BranchKind | null;
  domains?: string[] | null;
}

/**
 * AC-1030. How the shadow window is going over the filtered range, computed by the
 * endpoint over the shadow rows joined to their live rows - not in the browser, which
 * only ever holds one page.
 *
 * Parities are fractions (0 to 1). Null on a range with no shadow row to compare, which
 * the line says in words rather than printing "0%".
 */
export interface ShadowTurnSummary {
  count: number;
  branch_parity: number | null;
  asks_parity: number | null;
  /**
   * Whether `count` is the whole range or the endpoint's scan cap. A capped number read as
   * a complete one is the difference between "the new parser agreed on 96% of the window"
   * and "of the newest 5,000 turns in it".
   */
  truncated?: boolean;
}

export interface ChatbotTurnListResponse {
  items: ChatbotTurn[];
  /** Opaque; absent when there is no further page. */
  next_cursor?: string | null;
  /**
   * Whether Retry is wired in this environment at all (it deliberately is not, locally).
   * Rides the list because the screen needs it at the same moment it needs the turns, and
   * because a button that always 409s is what teaches an operator to distrust a screen.
   */
  retry_available?: boolean;
  retry_unavailable_reason?: string | null;
  /** AC-1030. Present only when the request filtered on `ingress=shadow`. */
  summary?: ShadowTurnSummary | null;
}

export interface ChatbotTurnFilters {
  contact_respond_id?: string;
  from?: string;
  to?: string;
  status?: TurnStatus;
  /**
   * AC-1029. Narrows to one arrival kind. `shadow` is what the console's Shadow filter
   * sends, and it is the only value that also brings back `summary`.
   */
  ingress?: TurnIngress;
  /** Page size. The endpoint defaults to 50 and caps at 200. */
  limit?: number;
  /** The previous page's opaque `next_cursor`. */
  cursor?: string | null;
}

export interface FailedContactFilters {
  from?: string;
  to?: string;
}

/** One contact with at least one failed turn in the range (AC-255). */
export interface FailedContactRow {
  contact_respond_id: string;
  last_failed_stage: TurnFailureStage | null;
  last_failed_at: string | null;
  count: number;
}

export interface FailedContactListResponse {
  items: FailedContactRow[];
}

export interface RetryTurnResponse {
  turn_id: string;
  /** What the RE-INJECTED turn will carry. The retried row keeps its own attempt. */
  attempt: number;
}

/**
 * `trace_detail` (chatbot growth r1, Slice D). Composed by the backend from
 * `trace` records, including `kind`-tagged entries the `data` / `dialogue`
 * lanes write as their slices land (`tool`, `crossdomain`, `reveals`, `decay`,
 * `focus`) plus an `open_question` entry. A kind this build has not shipped
 * yet renders as an empty section - `null` for a singleton, `[]` for a list -
 * never an error.
 */
export interface TurnDetailStage {
  name: string;
  started_at: string | null;
  ms: number | null;
  status: TraceStatus;
  summary: string | null;
  error: string | null;
}

export interface TurnDetailParse {
  raw: Record<string, unknown> | null;
  post_processed: Record<string, unknown> | null;
  prompt_version: number | string | null;
  model: string | null;
}

export interface TurnDetailDecay {
  slot: string | null;
  value: unknown;
  set_at_turn: number | null;
  age_turns: number | null;
  age_minutes: number | null;
  reason: string | null;
}

export interface TurnDetailOpenQuestion {
  before: unknown;
  answer: unknown;
  after: unknown;
  handler: string | null;
  outcome: string | null;
}

export interface TurnDetailFocus {
  slot: string | null;
  before: unknown;
  after: unknown;
  rule: string | null;
  source: string | null;
}

export interface TurnDetailTool {
  name: string | null;
  args: Record<string, unknown> | null;
  /** May carry `{truncated: true, bytes, head}` in place of the real envelope past 8 KB. */
  envelope: Record<string, unknown> | null;
  ms: number | null;
}

export interface TurnDetailCrossdomain {
  rung: number | null;
  tool: string | null;
  args: Record<string, unknown> | null;
  rows: number | null;
  rendered: boolean | null;
}

export interface TurnDetailReveals {
  restricted_fields_seen: string[];
  granted: string[];
  dropped: string[];
}

export interface TurnDetailSessionDiffEntry {
  key: string;
  change: 'gained' | 'lost';
}

export interface TurnDetailSession {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  diff: TurnDetailSessionDiffEntry[];
}

export interface TurnDetail {
  stages: TurnDetailStage[];
  parse: TurnDetailParse | null;
  decay: TurnDetailDecay[];
  open_question: TurnDetailOpenQuestion | null;
  focus: TurnDetailFocus[];
  tool: TurnDetailTool | null;
  crossdomain: TurnDetailCrossdomain[];
  reveals: TurnDetailReveals;
  session: TurnDetailSession;
}

export interface ChatbotTurnDetail extends ChatbotTurn {
  trace_detail: TurnDetail;
}
