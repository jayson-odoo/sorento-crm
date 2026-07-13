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
  /**
   * Internal respond_contacts.id when the write came from a portal/public-link contact.
   * Resolved to a human-readable name server-side (see user_display_name); never rendered raw.
   */
  contact_id?: string | null;
  /**
   * Resolved display name. Backend precedence: contact name (portal/public writes) →
   * staff name (authenticated user) → "System" (X-API-Key automation).
   */
  user_display_name?: string | null;
  changed_at: string; // ISO datetime
  old_values?: Record<string, unknown> | null;
  new_values?: Record<string, unknown> | null;
  description?: string | null;
  ip_address?: string | null;
}

export type AuditLogListResponse = DataGridApiResponse<AuditLog>;
