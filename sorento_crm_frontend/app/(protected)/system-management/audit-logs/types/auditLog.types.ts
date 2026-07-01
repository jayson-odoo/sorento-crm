import type { DataGridApiResponse } from '@/components/ui/data-grid';

/**
 * A single audit-trail entry ("who changed what").
 * Mirrors the backend `AuditLogResponse` schema
 * (sorento_crm_backend/app/schemas/audit.py).
 */
export interface AuditLog {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string; // INSERT | UPDATE | DELETE | CREATE
  user_id?: string | null;
  /** Resolved display name from users.name (or "System" for backend-driven changes). */
  user_display_name?: string | null;
  changed_at: string; // ISO datetime
  old_values?: Record<string, unknown> | null;
  new_values?: Record<string, unknown> | null;
  description?: string | null;
  ip_address?: string | null;
}

export type AuditLogListResponse = DataGridApiResponse<AuditLog>;
