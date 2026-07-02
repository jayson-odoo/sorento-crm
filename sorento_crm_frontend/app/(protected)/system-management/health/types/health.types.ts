/**
 * System Health dashboard types.
 *
 * Backend contract: `GET /api/v1/system/health/summary` -> `HealthSummaryResponse`.
 * Every metric block is nullable: a missing/legacy source table omits the block
 * (the FE renders an empty state for a null block, never an error).
 */
export interface EmailOutboxHealth {
  pending: number;
  sent: number;
  failed: number;
  cancelled: number;
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

export interface IntegrationChannelHealth {
  channel: string;
  success: number;
  failed: number;
  total: number;
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
