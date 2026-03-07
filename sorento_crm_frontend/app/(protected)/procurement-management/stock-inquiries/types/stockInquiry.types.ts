export interface StockInquiry {
  id: string;
  salesperson?: string | null;
  product_code?: string | null;
  item_description?: string | null;
  project_customer?: string | null;
  project_name?: string | null;
  quantity?: string | null;
  delivery_date?: string | null;
  remark?: string | null;
  additional_remark?: string | null;
  purchasing_response?: string | null;
  contact_id?: string | null;
  space_id?: string | null;
  respond_inbox_url?: string | null;
  status?: string | null;
  last_responded_by?: string | null;
  last_responded_by_name?: string | null;
  last_responded_at?: string | null;
  attachments?: StockInquiryAttachment[];
  created_at: Date;
  updated_at: Date;
}

export interface StockInquiryAttachment {
  id: string;
  inquiry_id: string;
  attachment_id?: string | null;
  file_name?: string | null;
  original_filename?: string | null;
  file_url?: string | null;
  file_size_bytes?: number | null;
  uploaded_at?: string | Date | null;
  link_type?: string | null;
}

export interface StockInquiryFormData {
  salesperson?: string;
  product_code?: string;
  item_description?: string;
  project_customer?: string;
  project_name?: string;
  quantity?: string;
  delivery_date?: string;
  remark?: string;
  additional_remark?: string;
  purchasing_response?: string;
  contact_id?: string;
  space_id?: string;
}

export interface StockInquiryDetail extends StockInquiry {}
