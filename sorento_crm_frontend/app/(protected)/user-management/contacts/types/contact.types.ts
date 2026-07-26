export interface RespondContactAccessType {
  code: string;
  name: string;
  sort_order?: number | null;
}

export interface RespondContact {
  id: string;
  phone_number: string;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  respond_io_id?: string | null;
  workspace_id?: string | null;
  workspace_name?: string | null;
  workspace_space_id?: string | null;
  access_type_codes?: string[];
  /** AC-F4: their sponsorship form demands a registered project. */
  requires_registered_project?: boolean;
  access_types?: RespondContactAccessType[];
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
}

export interface RespondContactFormData {
  phone_number: string;
  name?: string;
  workspace_id?: string | null;
  access_type_codes?: string[];
  /** AC-F4: their sponsorship form demands a registered project. */
  requires_registered_project?: boolean;
}
