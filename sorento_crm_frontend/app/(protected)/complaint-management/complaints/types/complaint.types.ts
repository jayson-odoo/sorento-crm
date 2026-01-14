export interface ComplaintAttachment {
  id: string;
  complaint_id: string;
  file_name?: string | null;
  file_url?: string | null;
  file_size_bytes?: number | null;
  uploaded_at: Date;
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
  attachments?: ComplaintAttachment[];
}

export interface ComplaintDetail extends Complaint {
  attachments: ComplaintAttachment[];
}
