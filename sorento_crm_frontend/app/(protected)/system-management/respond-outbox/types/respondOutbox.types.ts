export interface RespondOutboxRow {
  id: string;
  created_at: string;
  business_table?: string | null;
  business_id?: string | null;
  contact_identifier?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  sent_as: 'text' | 'template';
  message_text?: string | null;
  template_name?: string | null;
  button_url?: string | null;
  status: string; // success | failed | pending | processing
  status_code?: number | null;
  error_message?: string | null;
  response_payload?: string | null;
  created_by?: string | null;
}
