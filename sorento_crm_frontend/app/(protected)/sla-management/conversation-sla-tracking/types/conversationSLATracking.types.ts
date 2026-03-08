export interface ContactSimple {
  id: string;
  phone_number: string;
  name?: string | null;
  /** Respond.io contact id for inbox URL (e.g. https://app.respond.io/space/364817/inbox/{respond_io_id}) */
  respond_io_id?: string | null;
}

export interface UserSimple {
  id: string;
  email: string;
  name?: string | null;
  /** Superior of this user (e.g. for assignee tooltip in SLA tracking). */
  superior?: { name?: string | null; email?: string | null } | null;
}

export interface SLAPolicySimple {
  id: string;
  code: string;
  name: string;
}

export interface ConversationSLATracking {
  id: string;
  policy_id: string;
  policy_code?: string;
  policy_name?: string;
  policy?: SLAPolicySimple | null;
  current_tier: number;
  assigned_to?: string | null; // Keep for backward compatibility
  assigned_to_id?: string | null;
  initiated_at: Date;
  current_tier_started_at: Date;
  due_at: Date; // Due at (response): deadline to respond
  due_at_resolution?: Date | string | null; // Due at (resolution): deadline to resolve
  escalated_at?: Date | null;
  escalation_reason?: string | null;
  is_responded?: boolean;
  responded_at?: Date | null;
  response_time?: number | null;
  is_resolved: boolean;
  resolved_at?: Date | null;
  resolved_by?: string | null;
  created_at: Date;
  updated_at: Date;
  respond_contact_id?: string | null;
  /** Respond.io contact id for inbox URL (e.g. https://app.respond.io/space/364817/inbox/{respond_io_id}) */
  respond_io_id?: string | null;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  resolution_duration?: number | null;
  // Relationship objects
  contact?: ContactSimple | null;
  assigned_user?: UserSimple | null;
  // Computed fields for easy access
  contact_phone?: string | null;
  contact_name?: string | null;
  assigned_user_name?: string | null;
  assigned_user_email?: string | null;
  assigned_user_superior_name?: string | null;
  assigned_user_superior_email?: string | null;
  responded_by_user_name?: string | null;
  resolved_by_user_name?: string | null;
  average_response_time?: number | null;
  average_resolution_time?: number | null;
  // Time-in-tier and time-remaining (backend-computed; response stops when is_responded, resolution when is_resolved)
  time_in_tier_response_seconds?: number | null;
  time_remaining_response_seconds?: number | null;
  time_in_tier_resolution_seconds?: number | null;
  time_remaining_resolution_seconds?: number | null;
  resolution_due_at?: Date | string | null; // Alias / computed resolution deadline
  tier_response_hours?: number | null;
  tier_resolution_hours?: number | null;
}

export interface ConversationSLATrackingDetail extends ConversationSLATracking {
  event_logs?: ConversationSLAEventLog[];
  // Explicitly repeated so detail response type includes superior fields (backend returns these)
  assigned_user_superior_name?: string | null;
  assigned_user_superior_email?: string | null;
}

export interface ConversationSLAEventLog {
  id: string;
  sla_tracking_id: string;
  event_type: string;
  from_tier?: number | null;
  to_tier?: number | null;
  event_at: Date;
  from_time?: Date | null; // For response/resolution events, stores initiated_at
  duration?: number | null; // Duration in hours, calculated for response/resolution events
  reason?: string | null;
  assigned_to?: string | null; // Keep for backward compatibility
  assigned_to_id?: string | null;
  due_at?: Date | null;
  response_time?: number | null;
  resolution_time?: number | null;
  reminder_count: number;
  last_reminder_at?: Date | null;
  created_at: Date;
  // Related objects
  assigned_user?: UserSimple | null;
  // Computed fields
  assigned_user_name?: string | null;
  assigned_user_email?: string | null;
}

export interface SLATrackingDashboardMetrics {
  total_trackings: number;
  pending_count: number;
  responded_count: number;
  responded_not_resolved_count: number;
  resolved_count: number;
  escalated_count: number;
  overdue_at_response_count: number;
  overdue_at_resolution_count: number;
  average_response_time: number;
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
    responded_not_resolved: number;
    pending: number;
  };
  pending_response_overdue_breakdown: {
    not_yet_overdue: number;
    overdue_at_response: number;
  };
  responded_resolution_overdue_breakdown: {
    not_yet_overdue: number;
    overdue_at_resolution: number;
  };
  response_resolution_trends: Array<{
    date: string;
    average_response_time: number;
    average_resolution_time: number;
  }>;
}
