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
  /**
   * Chatbot turn re-architecture (AC-1503, AC-1515): tier/default_ledgers. `language`
   * and `always_full_report` are gone (chatbot memory lane A, contract section 5) -
   * language is now a profile FACT (`chatbot_profile.facts.language`, see
   * `services/contactChatbotService.ts`), and `always_full_report` was dead.
   */
  chatbot_profile?: {
    tier?: string | null;
    default_ledgers?: string[] | null;
  } | null;
  /**
   * Per-contact context level (chatbot memory lane A, contract section 2): `off` |
   * `conversation` | `past` | `full`, or null to follow the system default. Replaces
   * `chatbot_recall_enabled`, which the S3 build stops reading and this contract stops
   * sending (the column itself stays, untouched, per Q1).
   */
  chatbot_memory_level?: 'off' | 'conversation' | 'past' | 'full' | null;
  /** S6: may this contact ask the chatbot for stock. A CRM fact, default on. */
  chatbot_stock_allowed?: boolean;
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
