export interface ChatMessageRow {
  id: number;
  channel: string;
  /** Respond.io contact id. For filtering and thread lookup only — never displayed. */
  contact_id: string;
  /** Rendered "Name (+phone)". This is what the UI shows. */
  contact_display: string;
  phone_number: string;
  type: 'incoming' | 'outgoing';
  message: string;
  sent_at: string;
  /** Authoritative Respond-side timestamp; null until the resolver fills it. */
  respond_ts: string | null;
  delivery_status: string | null;
  turn_id: string | null;
  message_id: string | null;
  /** Outgoing rows only: seconds from the incoming message of the same turn. */
  latency_seconds: number | null;
  webhook_lag_seconds: number | null;
  /**
   * Per-turn conversation state transition (v1), on INCOMING rows only and only on
   * the thread (transcript) endpoint. Opaque: {v, before, parser_raw, parser_applied,
   * after}. `after: null` means the turn wrote no state — a real signal, not `{}`.
   * The transcript derives an entities-lost/gained + cause-flags summary from this and
   * offers the raw document in a searchable JSON viewer.
   */
  state_trace?: StateTrace | null;
}

/** Opaque per-turn state-transition document. Shape owned by the n8n producer. */
export interface StateTrace {
  v?: number | string;
  before?: Record<string, unknown> | null;
  parser_raw?: Record<string, unknown> | null;
  parser_applied?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface ChatMessageListResponse {
  data: ChatMessageRow[];
  pagination: { total: number; page: number };
  empty: boolean;
}

export interface ChatThreadResponse {
  data: ChatMessageRow[];
  contact_display: string;
  empty: boolean;
}

export interface ChatHistoryFilters {
  date_from?: string;
  date_to?: string;
  contact_id?: string;
  direction?: 'incoming' | 'outgoing';
  search?: string;
  breached_only?: boolean;
}

/**
 * Grouping the listing applies.
 *
 * Server-side, not a rendering choice: the grid is offset-paginated, so unless
 * the API orders group members contiguously the UI could only group within the
 * current page — every page would show fragments of many groups.
 */
export type ChatHistoryGroupBy = 'none' | 'date' | 'contact' | 'contact_date';
