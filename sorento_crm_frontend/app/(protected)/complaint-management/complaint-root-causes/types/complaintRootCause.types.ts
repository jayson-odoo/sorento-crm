export interface ComplaintRootCause {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
  complaint_count?: number;
}

export interface ComplaintRootCauseFormData {
  name: string;
  description?: string;
  is_active: boolean;
}
