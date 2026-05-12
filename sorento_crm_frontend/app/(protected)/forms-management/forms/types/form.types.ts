export interface Form {
  id: string;
  code: string;
  name: string;
  form_type: string;
  purpose?: string | null;
  language: string;
  version: number;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  attachment_id?: string | null;
  access_levels?: string[] | null;
  attachment?: {
    id: string;
    original_filename: string;
    stored_filename: string;
    file_path: string;
    file_size_bytes: number | null;
    mime_type: string | null;
    attachment_type?: {
      id: string;
      type_name: string;
    } | null;
  } | null;
}

export interface FormSection {
  id: string;
  form_id: string;
  section_name: string;
  section_order: number;
  created_at: Date;
  fields?: FormField[];
}

export interface FormField {
  id: string;
  section_id: string;
  field_name: string;
  field_label: string;
  field_type: 'text' | 'textarea' | 'number' | 'email' | 'phone' | 'date' | 'date_range' | 'dropdown' | 'radio' | 'checkbox' | 'multi_select' | 'file' | 'richtext' | 'signature';
  is_required: boolean;
  help_text?: string | null;
  placeholder?: string | null;
  validation_rule?: string | null;
  min_length?: number | null;
  max_length?: number | null;
  default_value?: string | null;
  conditional_logic?: Record<string, unknown> | null;
  field_order: number;
  created_at: Date;
}

export interface FormFormData {
  code: string;
  name: string;
  form_type?: string;
  purpose?: string;
  language: string;
  is_active: boolean;
  attachment_id?: string | null;
  access_levels?: string[] | null;
}

export interface FormVersion {
  id: string;
  form_id: string;
  version_number: number;
  structure: Record<string, unknown>;
  created_at: Date;
  created_by?: string | null;
  change_summary?: string | null;
  is_active: boolean;
}
