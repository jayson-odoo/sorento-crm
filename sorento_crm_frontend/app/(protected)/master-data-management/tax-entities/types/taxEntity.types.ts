export interface TaxEntity {
  id: string;
  tax_entity_id: string;
  name: string | null;
  tin: string | null;
  identity_no: string | null;
  tax_branch_id: string | null;
  tax_classification: number | null;
  gst_register_no: string | null;
  sst_register_no: string | null;
  tourism_tax_register_no: string | null;
  trade_name: string | null;
  business_activity_desc: string | null;
  msic_code: string | null;
  address: string | null;
  post_code: string | null;
  city: string | null;
  state_code: string | null;
  country_code: string | null;
  phone: string | null;
  email_address: string | null;
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
