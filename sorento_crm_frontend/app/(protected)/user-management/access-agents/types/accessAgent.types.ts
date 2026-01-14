export interface AccessAgent {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  pic_respond_user_id?: string | null;
}

export interface AccessAgentFormData {
  code: string;
  name: string;
  description?: string;
  pic_respond_user_id?: string;
  is_active: boolean;
}

export interface AccessAgentDetail extends AccessAgent {
  contact_accesses_count?: number;
  contact_accesses?: ContactAgentAccess[];
}

export interface ContactAgentAccess {
  id: string;
  respond_contact_id: string;
  agent_id: string;
  is_allowed: boolean;
  valid_from?: Date | null;
  valid_to?: Date | null;
  created_at: Date;
  created_by?: string | null;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  updated_at?: Date | null;
}

export interface ContactAgentAccessFormData {
  respond_contact_id: string;
  agent_id: string;
  is_allowed: boolean;
  valid_from?: Date;
  valid_to?: Date;
}
