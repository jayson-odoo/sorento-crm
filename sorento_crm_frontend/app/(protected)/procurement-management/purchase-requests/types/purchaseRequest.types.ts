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
  created_at?: string | null;
  updated_at?: string | null;
  lines?: PurchaseRequestLine[];
}

export interface PurchaseRequestLineFormData {
  item_code?: string;
  quantity?: number;
  remark?: string;
}

export interface PurchaseRequestFormData {
  request_type: string;
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
