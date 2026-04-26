/** Global master quotations table (Commercial → Quotations). */

export type QuotationStageBrief = {
  stage_code: string;
  stage_name: string;
  is_terminal?: boolean;
};

export type MasterQuotationTableRow = {
  id: string;
  tender_code: string;
  quotation_code: string;
  title: string;
  project_id: string;
  project_title: string;
  lead_id: string;
  lead_code: string;
  client_name?: string | null;
  quotation_stage?: QuotationStageBrief | null;
  owner_user_id?: string | null;
  owner_name?: string | null;
  quoted_amount?: string | null;
  quoted_currency?: string | null;
  /** When set, list label is `quotation_code` + `-` + this (aligned with quotation workspace header). */
  current_working_revision_number?: number | null;
  created_at: string;
};
