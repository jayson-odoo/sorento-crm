export interface AuditLogEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  user_id: string | null;
  user_display_name?: string | null;
  changed_at: string;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  description: string | null;
  ip_address: string | null;
}

export interface AuditLogsResponse {
  data: AuditLogEntry[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
