export interface AccessAgent {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  assign_to_new_internal_contacts: boolean;
  created_at: Date;
  updated_at: Date;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
}

export interface AccessAgentFormData {
  code: string;
  name: string;
  description?: string;
  is_active: boolean;
  assign_to_new_internal_contacts: boolean;
}

export interface AccessAgentDetail extends AccessAgent {
  contact_accesses_count?: number;
  contact_accesses?: ContactAgentAccess[];
}

export interface ContactAgentAccess {
  id: string;
  respond_contact_phone: string;
  respond_contact_name?: string | null;
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
  respond_contact_phone: string;
  respond_contact_name?: string;
  agent_id: string;
  is_allowed: boolean;
  valid_from?: Date;
  valid_to?: Date;
}
