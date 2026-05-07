export interface ComplaintResolution {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
  complaint_count?: number;
}

export interface ComplaintResolutionFormData {
  name: string;
  description?: string;
  is_active: boolean;
}
