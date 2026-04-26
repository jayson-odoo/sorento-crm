export interface CommercialLead {
  id: string;
  lead_code: string;
  title: string;
  customer_id: string;
  customer_code?: string | null;
  customer_name?: string | null;
  customer_phone?: string | null;
  customer_email?: string | null;
  owner_user_id?: string | null;
  owner_name?: string | null;
  created_by_user_id?: string | null;
  created_by_name?: string | null;
  lead_stage_id: string;
  stage_code?: string | null;
  stage_name?: string | null;
  allows_conversion: boolean;
  is_terminal: boolean;
  qualification: Record<string, unknown>;
  qualification_summary?: string | null;
  respond_workspace_id?: string | null;
  has_project: boolean;
  project_id?: string | null;
  lead_project_count?: number;
  created_at: string;
  updated_at: string;
}

export interface CommercialLeadStage {
  id: string;
  stage_code: string;
  stage_name: string;
  sort_order: number;
  is_terminal: boolean;
  allows_conversion: boolean;
  created_at: string;
  updated_at: string;
  can_go_back: boolean;
  is_active: boolean;
  is_cancelled: boolean;
}

export interface CommercialLeadNote {
  id: string;
  lead_id: string;
  body: string;
  created_by_user_id?: string | null;
  created_by_name?: string | null;
  created_at: string;
}

export interface CommercialLeadCreatePayload {
  customer_id: string;
  title: string;
  owner_user_id: string;
  lead_code?: string | null;
  lead_stage_id?: string | null;
  respond_workspace_id?: string | null;
  qualification?: Record<string, unknown> | null;
  qualification_summary?: string | null;
}

export interface CommercialLeadUpdatePayload {
  title?: string;
  owner_user_id?: string | null;
  lead_stage_id?: string | null;
  respond_workspace_id?: string | null;
  qualification?: Record<string, unknown> | null;
  qualification_summary?: string | null;
}

export interface CommercialLeadConvertPayload {
  project_title: string;
  tender_title: string;
  tender_code?: string | null;
  forecast_amount?: number | null;
  forecast_currency?: string | null;
  pipeline_stage?: string | null;
  expected_close_on?: string | null;
}

export interface LeadRelatedProjectRow {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface LeadRelatedQuotationRow {
  project_title: string;
  tender_code: string;
  quotation_code: string;
  title: string;
  path_role: string;
  stage_name?: string | null;
  is_terminal?: boolean;
  is_cancelled?: boolean;
}

export interface LeadRelatedSalesOrderRow {
  sales_order_code?: string | null;
  tender_code: string;
  quotation_code: string;
  title: string;
  path_role: string;
  stage_name?: string | null;
  project_title?: string;
}

export interface LeadRelatedResponse {
  projects: LeadRelatedProjectRow[];
  quotations: LeadRelatedQuotationRow[];
  sales_orders: LeadRelatedSalesOrderRow[];
}

export interface RespondWorkspaceSelectItem {
  id: string;
  space_id: string;
  name: string | null;
}

export interface RespondContactBrief {
  id: string;
  phone_number: string;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  respond_io_id?: string | null;
  access_type_code?: string | null;
  respond_workspace_id: string;
}

export interface LeadRespondContactRow {
  id: string;
  lead_id: string;
  respond_contact_id: string;
  contact_role: 'main' | 'stakeholder';
  sort_order: number;
  created_at: string;
  updated_at: string;
  contact: RespondContactBrief;
}
