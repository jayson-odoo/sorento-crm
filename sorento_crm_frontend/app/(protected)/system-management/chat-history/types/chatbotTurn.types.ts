/**
 * The turn trace shown under each incoming message in the Chat History drawer.
 *
 * Mirrors `chatbot.turns` (backend `app/models/chatbot_turn.py`). Field names follow the
 * wire, not frontend taste: a rename here is a contract break with the endpoint and with
 * the 1,535 captured fixtures the engine is graded against.
 */

/** The eight stages a turn can record, in the order the timeline renders them. */
export const TURN_STAGES = [
  'received',
  'understood',
  'access',
  'routed',
  'looked_up',
  'replied',
  'remembered',
  'sent',
] as const;
export type TurnStage = (typeof TURN_STAGES)[number];

/**
 * Where a turn stopped. A superset of `TurnStage`: three failure points sit outside the
 * timeline - `intake` is before the first trace record exists, `queued` is the per-contact
 * wait, `casual_llm` is the small-talk clarifier.
 */
export type TurnFailureStage = TurnStage | 'intake' | 'queued' | 'casual_llm';

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
export interface TurnTraceRecord {
  stage: TurnStage;
  status: TraceStatus;
  started_at: string;
  ms: number;
  summary: string;
  why: string;
  /** Small flat dict rendered as key/value rows under the sentences. */
  facts: Record<string, unknown>;
  error: string | null;
  /** Technical payload for the "Technical details" viewer. Byte-capped by the engine. */
  raw: unknown;
}

/** The answer the turn returned. Null while the turn is still running, or when it failed. */
export interface TurnResponseBody {
  ctx?: Record<string, unknown> | null;
  item?: Record<string, unknown> | null;
  reply?: { text?: string | null; quick_replies?: unknown[] } | null;
  actions?: Record<string, unknown>[] | null;
}

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
  created_at: string;
  finished_at: string | null;
  trace: TurnTraceRecord[];
  response: TurnResponseBody | null;
  /**
   * True when this delivery was a repeat of a respond message already turned into a turn
   * (the webhook producer and the failover poller are two injectors of one message).
   * Derived by the endpoint, not a column.
   */
  duplicate?: boolean;
}

export interface ChatbotTurnListResponse {
  items: ChatbotTurn[];
  /** Opaque; absent when there is no further page. */
  next_cursor?: string | null;
}

export interface ChatbotTurnFilters {
  contact_respond_id?: string;
  from?: string;
  to?: string;
  status?: TurnStatus;
}

export interface RetryTurnResponse {
  turn_id: string;
  attempt: number;
}
