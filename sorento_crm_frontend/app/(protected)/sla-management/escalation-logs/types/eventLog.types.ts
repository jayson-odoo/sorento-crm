export interface ConversationSLAEventLog {
  id: string;
  sla_tracking_id: string;
  event_type: string;
  from_tier?: number | null;
  to_tier?: number | null;
  event_at: Date;
  reason?: string | null;
  assigned_to?: string | null;
  due_at?: Date | null;
  response_time?: number | null;
  resolution_time?: number | null;
  reminder_count: number;
  last_reminder_at?: Date | null;
  created_at: Date;
}
