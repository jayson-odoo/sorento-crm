export interface ContactAccessAgent {
  id: string;
  /** The contact this grant belongs to. Null on legacy rows keyed by phone only. */
  respond_contact_id?: string | null;
  respond_contact_phone: string;
  respond_contact_name?: string | null;
  /**
   * The CONTACT's outbound kill switch, repeated on each of that contact's grant
   * rows. Null when no contact row is linked, which is "unknown", not "reachable".
   */
  outbound_enabled?: boolean | null;
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
