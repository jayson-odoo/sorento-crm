export interface RespondContact {
  id: string;
  phone_number: string;
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  user_type?: string | null;
  access_type_code?: string | null;
  respond_io_id?: string | null;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
}

export interface RespondContactFormData {
  phone_number: string;
  name?: string;
  user_type?: string | null;
}
