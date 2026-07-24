/**
 * System Health dashboard types.
 *
 * Backend contract: `GET /api/v1/system/health/summary` -> `HealthSummaryResponse`.
 * Every metric block is nullable: a missing/legacy source table omits the block
 * (the FE renders an empty state for a null block, never an error).
 */
export interface EmailOutboxHealth {
  /** Lifetime ledger totals — NOT windowed. Shown alongside the windowed count so
   *  an all-time figure never reads as a live incident. */
  pending: number;
  sent: number;
  failed: number;
  cancelled: number;
  /** Failures whose rows were created inside the selected window. */
  failed_in_window: number;
  failed_last_24h: number;
}

export interface ImportsHealth {
  total_last_24h: number;
  finished_last_24h: number;
  failed_last_24h: number;
  success_rate: number; // percent
}

export interface ScheduledTasksHealth {
  total: number;
  overdue: number;
  last_run_failed: number;
}

/** One distinct fault behind a channel's `failed` count. */
export interface FailureSignature {
  /** Normalised grouping key (ids/timestamps masked) — not for display. */
  signature: string;
  /** A real un-masked message, safe to paste into a log search. */
  sample_message: string;
  status_code: number | null;
  count: number;
  /**
   * Literal substrings shared by every row in this group, AND-ed by the
   * drill-down filter. Not `sample_message` — that embeds a record id and would
   * select the single row it came from.
   *
   * A list rather than one substring: the longest single run of one fault can
   * also be a prefix of a different fault (401 on /message vs /conversation/status),
   * which returned 433 rows for a group of 428. Empty when nothing stable exists.
   */
  filter_terms: string[];
}

export interface IntegrationChannelHealth {
  channel: string;
  success: number;
  failed: number;
  /** Logged as failed but expected (e.g. an idempotency race). */
  benign: number;
  /** Still in progress. Previously counted in `total` but rendered nowhere. */
  in_flight: number;
  total: number;
  /** The distinct faults behind `failed`, worst first (max 3). */
  top_failures: FailureSignature[];
}

export interface IntegrationsHealth {
  channels: IntegrationChannelHealth[];
}

export interface AuditTrendPoint {
  date: string; // YYYY-MM-DD (UTC)
  count: number;
}

export interface AuditActivityHealth {
  count_last_24h: number;
  daily_trend: AuditTrendPoint[];
}

export interface HealthSummary {
  generated_at: string;
  email_outbox: EmailOutboxHealth | null;
  imports: ImportsHealth | null;
  scheduled_tasks: ScheduledTasksHealth | null;
  integrations: IntegrationsHealth | null;
  audit_activity: AuditActivityHealth | null;
}
