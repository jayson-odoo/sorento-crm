export interface AuditLogEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  user_id: string | null;
  user_display_name?: string | null;
  /** Acting contact for a portal / public write (legacy rows carry no actor_type). */
  contact_id?: string | null;
  /** user | contact | integration | worker | scheduler | public_link | system | legacy */
  actor_type?: string | null;
  /** password | phone_otp | portal_link | portal_token | api_key | impersonation | dev_login */
  auth_method?: string | null;
  /** Who was at the keyboard; differs from user_id only when impersonating. Never rendered raw. */
  real_user_id?: string | null;
  integration_id?: string | null;
  job_id?: string | null;
  /** Actor resolved to words server-side, e.g. "Aisyah (phone)". */
  actor_label?: string | null;
  changed_at: string;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  description: string | null;
  ip_address: string | null;
  /** The record in words; for a child row on its parent's trail, e.g. "Product line CWCY604". */
  entity_label?: string | null;
  root_entity_type?: string | null;
  root_entity_id?: string | null;
}

export interface AuditLogsResponse {
  data: AuditLogEntry[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
