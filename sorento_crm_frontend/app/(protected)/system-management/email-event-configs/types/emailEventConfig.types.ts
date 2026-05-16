export interface EmailEventConfig {
  event_key: string;
  display_name: string;
  description?: string | null;
  enabled: boolean;
  rate_per_window_override?: number | null;
  window_seconds_override?: number | null;
  priority_override?: number | null;
  coalesce_window_seconds_override?: number | null;
  created_at: string;
  updated_at: string;
}

export interface EmailEventConfigUpdate {
  enabled?: boolean;
  rate_per_window_override?: number | null;
  window_seconds_override?: number | null;
  priority_override?: number | null;
  coalesce_window_seconds_override?: number | null;
}
