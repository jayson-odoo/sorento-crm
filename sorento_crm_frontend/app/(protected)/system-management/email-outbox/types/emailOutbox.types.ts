export type EmailOutboxStatus =
  | 'pending'
  | 'sending'
  | 'sent'
  | 'failed'
  | 'cancelled'
  | 'deferred'
  | string;

export interface EmailOutboxRow {
  id: string;
  event_key: string;
  recipient_email: string;
  recipients_json?: { to?: string[]; cc?: string[]; bcc?: string[] } | null;
  subject: string;
  body_text?: string | null;
  body_html?: string | null;
  from_name?: string | null;
  metadata?: Record<string, unknown> | null;
  priority: number;
  status: EmailOutboxStatus;
  scheduled_for: string;
  sent_at?: string | null;
  attempt_count: number;
  max_attempts: number;
  error_message?: string | null;
  cancel_reason?: string | null;
  coalesce_key?: string | null;
  created_at: string;
  updated_at: string;
}
