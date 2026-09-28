export interface RespondContactAccessType {
  code: string;
  name: string;
  sort_order?: number | null;
}

export interface RespondContact {
  id: string;
  phone_number: string;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  respond_io_id?: string | null;
  workspace_id?: string | null;
  workspace_name?: string | null;
  workspace_space_id?: string | null;
  access_type_codes?: string[];
  /** AC-F4: their sponsorship form demands a registered project. */
  requires_registered_project?: boolean;
  access_types?: RespondContactAccessType[];
  /** Outbound WhatsApp kill switch. Flipped via the shared outbound endpoints, not a contact update. */
  outbound_enabled?: boolean;
  /** Chatbot turn re-architecture (AC-1503, AC-1515): tier/language/default_ledgers. */
  chatbot_profile?: {
    tier?: string | null;
    language?: string | null;
    default_ledgers?: string[] | null;
    always_full_report?: boolean;
  } | null;
  /** Same-contact episode recall, D3: per-contact toggle, global default off. */
  chatbot_recall_enabled?: boolean;
  /** S6: may this contact ask the chatbot for stock. A CRM fact, default on. */
  chatbot_stock_allowed?: boolean;
  /** Identity S3: the user this contact is linked to, if any (list rows). Null
   *  without `user_management.users.view`. */
  linked_user_id?: string | null;
  linked_user_name?: string | null;
  /** Identity S3: which role the Add user form should suggest for this contact
   *  (S3 contract 1.1) - a market-segment or sales-agent salesperson, else a
   *  portal user. */
  is_salesperson?: boolean;
  suggested_role_slug?: 'salesperson' | 'portal_user';
  /** Identity S3: the full linked user (contact detail only), or null when
   *  unlinked or the caller lacks `user_management.users.view`. */
  linked_user?: {
    id: string;
    name: string | null;
    email: string | null;
    status: string;
    has_password: boolean;
    roles: { id: string; name: string }[];
    /** True when the user's phone is not the contact's (or is empty), so the
     *  WhatsApp code cannot reach that user (fix round 2, S3). */
    phone_differs_from_contact?: boolean;
  } | null;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
}

export interface RespondContactFormData {
  phone_number: string;
  name?: string;
  workspace_id?: string | null;
  access_type_codes?: string[];
  /** AC-F4: their sponsorship form demands a registered project. */
  requires_registered_project?: boolean;
}
