export interface ContactAccessAgent {
  id: string;
  respond_contact_id: string;
  agent_id: string;
  agent_code?: string;
  agent_name?: string;
  is_allowed: boolean;
  valid_from?: Date | null;
  valid_to?: Date | null;
  created_at: Date;
  created_by?: string | null;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  updated_at?: Date | null;
}
