export interface CommercialProjectTaskBoardTask {
  id: string;
  template_node_id?: string | null;
  title: string;
  description?: string | null;
  category?: string | null;
  category_code?: string | null;
  parent_task_id?: string | null;
  parent_template_node_id?: string | null;
  sort_order?: number;
  status_code?: string | null;
  is_service_task?: boolean;
  assignee_user_id?: string | null;
  lead_time_days?: number | null;
  dependency_task_ids?: string[];
  start_date?: string | null;
  end_date?: string | null;
}

export interface CommercialProjectTaskBoard {
  template_id?: string | null;
  template_name?: string | null;
  template_version?: number | null;
  tasks?: CommercialProjectTaskBoardTask[];
}

/** Same JSON shape as `CommercialProjectTaskBoard` (used on projects and master quotations). */
export type CommercialEntityTaskBoard = CommercialProjectTaskBoard;

export interface CommercialProjectDocumentRow {
  id: string;
  name: string;
  size_bytes?: number | null;
  uploaded_by?: string | null;
  uploaded_at: string;
  file_path: string;
}

export interface CommercialProjectTaskTemplateRow {
  id: string;
  name: string;
  description?: string | null;
  version_number: number;
}

export interface CommercialProjectStageSummary {
  id: string;
  code: string;
  label: string;
  sort_order: number;
  is_terminal: boolean;
  can_go_back: boolean;
}

export interface CommercialProjectMember {
  name: string;
  tags: string[];
}

export interface CommercialProjectCustomerContact {
  id?: string | null;
  name: string;
  phone?: string | null;
  email?: string | null;
}

export interface CommercialProjectListRow {
  id: string;
  title: string;
  brief?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status: string;
  project_stage_id: string;
  project_stage_code?: string | null;
  project_stage_name?: string | null;
  lead_id: string | null;
  lead_code: string | null;
  customer_code: string | null;
  customer_name: string | null;
  customer_ids?: string[];
  project_lead_count?: number;
  project_leads?: Array<{
    id: string;
    lead_code?: string | null;
    lead_title?: string | null;
    customer_id?: string | null;
    customer_name?: string | null;
  }>;
  lead_project_count?: number;
  owner_user_id: string;
  owner_user_ids: string[];
  owner_name: string | null;
  owner_names: string[];
  developer_customer_id: string;
  developer_customer_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CommercialProjectMasterQuotationRow {
  id: string;
  tender_code: string;
  quotation_code: string;
  sales_order_code?: string | null;
  title: string;
  path_role: string;
  lead_id?: string | null;
  lead_code?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  quotation_stage?: {
    stage_code: string;
    stage_name: string;
    is_terminal?: boolean;
    is_cancelled?: boolean;
  } | null;
  current_working_revision_number?: number | null;
  final_selected_revision_number?: number | null;
  quoted_amount?: string | null;
  quoted_currency?: string | null;
  owner_name?: string | null;
  created_at?: string | null;
}

export interface CommercialProjectTenderSummary {
  id: string;
  tender_code: string;
  title: string;
  forecast_amount: string | null;
  forecast_currency: string | null;
  pipeline_stage: string | null;
  expected_close_on: string | null;
  master_quotation_count: number;
}

export interface CommercialProjectDetail extends CommercialProjectListRow {
  lead_id: string | null;
  lead_title: string | null;
  lead_stage_code: string | null;
  lead_stage_name: string | null;
  customer_id: string | null;
  address_line_1?: string | null;
  address_line_2?: string | null;
  postcode?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  customer_ids?: string[];
  project_customers?: Array<{ id: string; customer_code?: string | null; customer_name?: string | null }>;
  project_leads?: Array<{
    id: string;
    lead_code?: string | null;
    lead_title?: string | null;
    customer_id?: string | null;
    customer_name?: string | null;
  }>;
  notes?: string | null;
  project_stage?: CommercialProjectStageSummary | null;
  project_members: CommercialProjectMember[];
  project_customer_contacts: CommercialProjectCustomerContact[];
  task_template_id?: string | null;
  task_board: CommercialProjectTaskBoard;
  tenders: CommercialProjectTenderSummary[];
  tender_count: number;
  forecast_by_currency: Record<string, string>;
  quotation_execution_state_counts: Record<string, number>;
  /** Sum of master quotation quoted_amount where stage is not terminal */
  open_quotation_amount_by_currency?: Record<string, string>;
  /** Sum of master quotation quoted_amount where stage is terminal (final) */
  sales_order_amount_by_currency?: Record<string, string>;
  documents: CommercialProjectDocumentRow[];
}

export interface CommercialLeadOption {
  id: string;
  lead_code: string;
  title: string;
  stage_code: string | null;
}

export const COMMERCIAL_PROJECT_STATUS_OPTIONS = [
  { value: '__all__', label: 'All statuses' },
  { value: 'planning', label: 'Planning' },
  { value: 'active', label: 'Active' },
  { value: 'on_hold', label: 'On hold' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
] as const;
