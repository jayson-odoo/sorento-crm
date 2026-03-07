export type OutgoingMailStatus = 'pending' | 'sent' | 'failed' | string;

export interface OutgoingMail {
  id: string;
  notification_id: string;
  user_id: string;
  to_email: string;
  subject: string;
  body?: string | null;
  status: OutgoingMailStatus;
  created_at: string;
  sent_at?: string | null;
  error_message?: string | null;
  notification_type?: string | null;
  source_entity_type?: string | null;
  source_entity_id?: string | null;
  event_type?: string | null;
}

