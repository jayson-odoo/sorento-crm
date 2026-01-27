export interface ContactSimple {
  id: string;
  phone_number: string;
  name?: string | null;
}

export interface UserSimple {
  id: string;
  email: string;
  name?: string | null;
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
  due_at: Date;
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
}

export interface ConversationSLATrackingDetail extends ConversationSLATracking {
  event_logs?: ConversationSLAEventLog[];
}

export interface ConversationSLAEventLog {
  id: string;
  sla_tracking_id: string;
  event_type: string;
  from_tier?: number | null;
  to_tier?: number | null;
  event_at: Date;
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
