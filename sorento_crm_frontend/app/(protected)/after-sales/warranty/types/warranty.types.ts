export interface WarrantyPolicy {
  id: string;
  version: string;
  effective_from: string;
  effective_to: string | null;
  policy_text?: string | null;
  term_count: number;
}

export interface WarrantyPolicyValues {
  version: string;
  effective_from: string;
  effective_to: string | null;
  policy_text: string | null;
}

export interface SupersedeValues {
  version: string;
  effective_from: string;
  policy_text?: string | null;
}

export interface SupersedeResult {
  closed: WarrantyPolicy;
  created: WarrantyPolicy;
}

export interface WarrantyTerm {
  id: string;
  policy_id: string;
  kind_id: string;
  part_name: string;
  duration_months: number | null;
  is_lifetime: boolean;
  covered_defect_type_ids: string[] | null;
  installation_included: boolean;
  qualifications: string | null;
  exclusions: string | null;
}

export type WarrantyTermValues = Omit<WarrantyTerm, 'id'>;

export interface WarrantyKind {
  id: string;
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  rule_count: number;
  term_count: number;
}

export interface WarrantyKindValues {
  code: string;
  name: string;
  is_active?: boolean;
}

export type MatchType = 'series' | 'model_list' | 'category' | 'code_prefix';

export interface WarrantyRule {
  id: string;
  kind_id: string;
  kind_code: string;
  kind_name: string;
  match_type: MatchType;
  match_value: string;
  priority: number;
}

export interface WarrantyRuleValues {
  kind_id: string;
  match_type: MatchType;
  match_value: string;
  priority: number;
}

export interface KindRuleTestResult {
  resolved_kind: { id: string; code: string; name: string } | null;
  deciding_rule: { id: string; match_type: MatchType; match_value: string } | null;
}
