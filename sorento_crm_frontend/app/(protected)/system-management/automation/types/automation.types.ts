export interface RecipientConfig {
  user_ids: string[];
  role_ids: string[];
  include_promotion_owner: boolean;
  /** When set, also email the assigned customer-service PIC of the triggering
   * purchase request / sponsorship form (resolved from the active CS SLA stage). */
  include_assigned_cs_pic?: boolean;
  extra_emails: string[];
}

import type { RuleGroup } from '@/components/rule-builder/types';

export interface Automation {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  /** Optional condition tree filtering which trigger matches this automation
   * acts on. Null = match all. Wire shape mirrors the rule engine. */
  conditions_json: RuleGroup | null;
  action_type: string;
  email_template_id: string;
  email_template_name?: string | null;
  recipient_config: RecipientConfig;
  /** When true, a daily run matching multiple promotions sends one combined
   * email per recipient instead of one email per promotion. */
  group_matches: boolean;
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
  group_matches?: boolean;
  conditions_json?: RuleGroup | null;
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
  /** Rule-engine fact sources this trigger exposes. Non-empty ⇒ the automation
   * form renders the RuleBuilder so matches can be filtered. Absent/empty on
   * triggers that can't be filtered (backend may omit until wired). */
  fact_sources?: string[];
  /** True ⇒ several matches from one run can be folded into a single email per
   * recipient, so the form offers the "Combine into one email" switch and sends
   * group_matches. Absent/false on triggers where grouping means nothing. */
  supports_grouping?: boolean;
}

export interface ListResponse<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
