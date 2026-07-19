export type MatchType = 'exact_value' | 'exact_label' | 'exact_keyword' | 'normalized';

export interface LookupKeyword {
  id?: string;
  keyword: string;
  locale?: string | null;
}

export interface LookupOption {
  id: string;
  set_id: string;
  value: string;
  label: string;
  sort_order: number;
  is_active: boolean;
  description: string | null;
  keywords: LookupKeyword[];
  created_at: string;
  updated_at: string | null;
}

export interface LookupOptionFormData {
  value: string;
  label: string;
  sort_order: number;
  is_active: boolean;
  description?: string;
  keywords: LookupKeyword[];
}

export interface LookupSet {
  id: string;
  tenant_id: string | null;
  set_key: string;
  name: string;
  description: string | null;
  is_active: boolean;
  option_count: number;
  binding_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface LookupSetFormData {
  set_key: string;
  name: string;
  description?: string;
  is_active: boolean;
  initial_binding?: { table_name: string; column_name: string };
}

export interface LookupBinding {
  id: string;
  tenant_id: string | null;
  set_id: string;
  table_name: string;
  column_name: string;
  table_label: string | null;
  column_label: string | null;
  /** R2: option `value` the FE pre-selects on a NEW form bound to this field. */
  default_value: string | null;
  created_at: string;
}

export interface LookupEligibility {
  table_name: string;
  column_name: string;
  table_label: string;
  column_label: string;
  data_type: 'string' | 'int';
  nullable: boolean;
  is_bound: boolean;
}

export interface LookupResolveResponse {
  value: string;
  label: string;
  matched_keyword: string | null;
  match_type: MatchType;
  score: number;
}
