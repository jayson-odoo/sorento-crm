export interface RespondContact {
  id: string;
  phone_number: string;
  name?: string | null;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
}

export interface RespondContactFormData {
  phone_number: string;
  name?: string;
}
