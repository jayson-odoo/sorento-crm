export interface RecipientConfig {
  user_ids: string[];
  role_ids: string[];
  include_promotion_owner: boolean;
  extra_emails: string[];
}

export interface Automation {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  action_type: string;
  email_template_id: string;
  email_template_name?: string | null;
  recipient_config: RecipientConfig;
  schedule_type: 'manual' | 'daily';
  run_time: string | null;
  timezone: string;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  next_run_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationCreateBody {
  name: string;
  description?: string | null;
  enabled?: boolean;
  trigger_type: string;
  trigger_config?: Record<string, unknown>;
  action_type?: string;
  email_template_id: string;
  recipient_config?: RecipientConfig;
  schedule_type?: 'manual' | 'daily';
  run_time?: string | null;
  timezone?: string;
}

export type AutomationUpdateBody = Partial<AutomationCreateBody>;

export interface AutomationRun {
  id: string;
  automation_id: string;
  run_mode: 'manual' | 'scheduled';
  started_at: string;
  finished_at: string | null;
  status: 'running' | 'success' | 'partial' | 'failed';
  duration_ms: number | null;
  recipients_attempted: number;
  recipients_delivered: number;
  summary: Record<string, unknown> | null;
  error: string | null;
}

export interface AutomationRunNowResult {
  run_id: string;
  status: string;
  recipients_attempted: number;
  summary?: Record<string, unknown> | null;
}

export interface TriggerSpec {
  type: string;
  label: string;
  description: string;
  config_schema: Record<string, unknown>;
}

export interface ListResponse<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
