export interface TaxCode {
  id: string;
  tax_code: string;
  supply_purchase: string | null;
  tax_rate: string | number | null;
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
