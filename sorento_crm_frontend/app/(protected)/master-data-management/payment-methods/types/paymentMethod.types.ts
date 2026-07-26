export interface PaymentMethod {
  id: string;
  payment_method: string;
  description: string | null;
  bank_account: string | null;
  journal_type: string | null;
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
