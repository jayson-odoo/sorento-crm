export interface ConversationSLATracking {
  id: string;
  policy_id: string;
  policy_code?: string;
  policy_name?: string;
  current_tier: number;
  assigned_to?: string | null;
  initiated_at: Date;
  current_tier_started_at: Date;
  due_at: Date;
  escalated_at?: Date | null;
  escalation_reason?: string | null;
  is_resolved: boolean;
  resolved_at?: Date | null;
  resolved_by?: string | null;
  created_at: Date;
  updated_at: Date;
  respond_contact_id: string;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  resolution_duration?: number | null;
}

export interface ConversationSLATrackingDetail extends ConversationSLATracking {
  escalation_logs?: ConversationSLAEscalationLog[];
}

export interface ConversationSLAEscalationLog {
  id: string;
  sla_tracking_id: string;
  from_tier: number;
  to_tier: number;
  escalated_at: Date;
  reason: string;
  assigned_to?: string | null;
  due_at: Date;
  reminder_count: number;
  last_reminder_at?: Date | null;
  created_at: Date;
}

export interface SLATrackingDashboardMetrics {
  total_trackings: number;
  resolved_count: number;
  pending_count: number;
  escalated_count: number;
  average_resolution_time: number;
  escalation_rate: number;
  response_time_trends: Array<{
    date: string;
    average_response_time: number;
  }>;
  escalation_rates_by_tier: Array<{
    tier_level: number;
    escalation_count: number;
  }>;
  resolution_time_distribution: {
    resolved: number;
    unresolved: number;
  };
  status_breakdown: {
    resolved: number;
    escalated: number;
    pending: number;
  };
}
