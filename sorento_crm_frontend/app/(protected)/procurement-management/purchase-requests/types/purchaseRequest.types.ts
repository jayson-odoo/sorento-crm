export interface PurchaseRequestLine {
  id: string;
  purchase_request_id: string;
  item_code?: string | null;
  quantity?: number | null;
  remark?: string | null;
  sort_order?: number | null;
  created_at?: string | null;
}

export interface PurchaseRequest {
  id: string;
  request_type: string;
  request_number?: string | null;
  request_date?: string | null;
  customer_name?: string | null;
  project_title?: string | null;
  purpose?: string | null;
  expected_delivery_date?: string | null;
  expected_po_date?: string | null;
  expected_po_date_text?: string | null;
  requested_by?: string | null;
  requested_at?: string | null;
  status?: string | null;
  source?: string | null;
  external_reference?: string | null;
  contact_id?: string | null;
  space_id?: string | null;
  respond_inbox_url?: string | null;
  approver_user_id?: string | null;
  approver_email?: string | null;
  approver_display_name?: string | null;
  approval_status?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
  approval_signature_ref?: string | null;
  approval_comments?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  lines?: PurchaseRequestLine[];
}

export interface SendApprovalLinkRequest {
  approver_email?: string | null;
  approver_user_id?: string | null;
  expires_hours?: number;
  send_email?: boolean;
  base_url?: string | null;
}

export interface SendApprovalLinkResponse {
  approval_url: string;
  expires_at: string;
  token_id: string;
  email_sent?: boolean | null;
  email_error?: string | null;
}

export interface PurchaseRequestLineFormData {
  item_code?: string;
  quantity?: number;
  remark?: string;
}

export interface PurchaseRequestFormData {
  request_type: string;
  request_number?: string | null;
  request_date?: string;
  customer_name?: string;
  project_title?: string;
  purpose?: string;
  expected_delivery_date?: string;
  expected_po_date?: string;
  expected_po_date_text?: string;
  requested_by?: string;
  requested_at?: string;
  contact_id?: string | null;
  space_id?: string | null;
  products?: PurchaseRequestLineFormData[];
}

export interface PurchaseRequestDetail extends PurchaseRequest {}
