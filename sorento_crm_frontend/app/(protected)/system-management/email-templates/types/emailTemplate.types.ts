export interface EmailTemplate {
  id: string;
  code: string;
  name: string;
  description: string | null;
  subject: string;
  body_html: string;
  body_text: string | null;
  is_active: boolean;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateCreateBody {
  code: string;
  name: string;
  description?: string | null;
  subject: string;
  body_html: string;
  body_text?: string | null;
  is_active?: boolean;
}

export interface EmailTemplateUpdateBody {
  code?: string;
  name?: string;
  description?: string | null;
  subject?: string;
  body_html?: string;
  body_text?: string | null;
  is_active?: boolean;
}

export interface EmailTemplatePreview {
  subject: string;
  body_html: string;
  body_text: string;
}

export interface TemplateVariable {
  key: string;
  label: string;
  sample?: string | null;
}

export interface ListResponse<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
