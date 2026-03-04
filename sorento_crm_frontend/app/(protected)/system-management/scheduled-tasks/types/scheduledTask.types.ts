export interface ScheduledTask {
  id: string;
  key: string;
  name: string;
  description: string | null;
  enabled: boolean;
  interval_unit: string;
  interval_value: number;
  timezone: string;
  start_at: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduledTaskRun {
  id: string;
  task_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  duration_ms: number | null;
  summary: Record<string, unknown> | null;
  error: string | null;
}

export interface ScheduledTaskUpdateBody {
  name?: string;
  description?: string | null;
  enabled?: boolean;
  interval_unit?: string;
  interval_value?: number;
  timezone?: string;
  start_at?: string | null;
}

export interface ListResponse<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
