export interface ComplaintAttachment {
  id: string;
  complaint_id: string;
  attachment_id?: string | null;
  /** Original filename (from attachment). Prefer this for display. */
  file_name?: string | null;
  original_filename?: string | null;
  file_url?: string | null;
  file_size_bytes?: number | null;
  uploaded_at: Date;
  /** From complaint_attachments table */
  link_type?: 'complaint_attachment' | null;
}

export interface Complaint {
  id: string;
  delivery_order_number?: string | null;
  complaint_date?: Date | null;
  customer_type?: string | null;
  customer_type_others?: string | null;
  within_warranty?: string | null;
  product_type?: string | null;
  defects_discovered?: string | null;
  complaint_type?: string | null;
  defect_description?: string | null;
  product_code?: string | null;
  salesperson?: string | null;
  customer_name?: string | null;
  contact_person?: string | null;
  contact_number?: string | null;
  customer_address?: string | null;
  project_title?: string | null;
  contact_id?: string | null;
  space_id?: string | null;
  respond_inbox_url?: string | null;
  technical_team_response?: string | null;
  status?: string | null;
  last_responded_by?: string | null;
  last_responded_by_name?: string | null;
  last_responded_at?: string | null;
  created_at?: string | null;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  attachments: ComplaintAttachment[];
}

export interface ComplaintFormData {
  delivery_order_number?: string;
  complaint_date?: Date;
  customer_type?: string;
  customer_type_others?: string;
  within_warranty?: string;
  product_type?: string;
  defects_discovered?: string;
  complaint_type?: string;
  defect_description?: string;
  product_code?: string;
  salesperson?: string;
  customer_name?: string;
  contact_person?: string;
  contact_number?: string;
  customer_address?: string;
  project_title?: string;
  contact_id?: string | null;
  space_id?: string | null;
  technical_team_response?: string;
  status?: string;
  last_responded_by?: string;
  last_responded_at?: string;
  attachments?: ComplaintAttachment[];
}

export interface ComplaintDetail extends Complaint {
  attachments: ComplaintAttachment[];
}
