export interface SalesAgent {
  id: string;
  sales_agent: string;
  description: string | null;
  is_active: boolean;
  internal_note: string | null;
  follow_up: boolean;
  source: 'autocount' | 'manual';
  created_at: string;
  updated_at: string | null;
}

export interface MirrorAnnotationPayload {
  internal_note: string;
  follow_up: boolean;
}
