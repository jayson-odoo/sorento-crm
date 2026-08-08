export interface ComplaintResolution {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  /** Choosing this resolution raises a Service Job for the complaint, carrying the site
   *  the complaint reported. Data rather than code because Sorento owns this vocabulary
   *  and adds to it. */
  requires_service_job: boolean;
  created_at: string;
  updated_at?: string | null;
  complaint_count?: number;
}

export interface ComplaintResolutionFormData {
  name: string;
  description?: string;
  is_active: boolean;
  requires_service_job: boolean;
}
