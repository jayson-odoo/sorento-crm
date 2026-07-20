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
