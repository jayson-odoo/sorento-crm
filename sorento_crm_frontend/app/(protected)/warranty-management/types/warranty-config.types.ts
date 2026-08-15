/**
 * ============================================================================
 * Warranty configuration (S7b) - the shapes the three tabs read and write
 * ============================================================================
 * Mirrors `sorento_crm_backend/app/models/warranty.py` plus the read-side fields
 * the screens need in order to obey "no UUIDs in the UI": every id-bearing
 * relation is accompanied by a resolved human-readable label, and every
 * destructive action is accompanied by the count it is about to take with it.
 *
 * The authoritative request/response contract is documented at the top of
 * `services/warrantyConfigService.ts`.
 * ============================================================================
 */
import type { DataGridApiResponse } from '@/components/ui/data-grid';

/** Declared in `app.services.warranty_service.KIND_RULE_MATCH_TYPES`. */
export type KindRuleMatchType = 'category' | 'model_prefix' | 'model_list' | 'series';

/** Ranked narrowest-first: `KIND_RULE_SPECIFICITY` in the engine. */
export const KIND_RULE_MATCH_TYPES: KindRuleMatchType[] = [
  'model_list',
  'model_prefix',
  'series',
  'category',
];

export const KIND_RULE_MATCH_TYPE_LABEL: Record<KindRuleMatchType, string> = {
  model_list: 'Model list',
  model_prefix: 'Model prefix',
  series: 'Series',
  category: 'Category',
};

/** The `{id, code, name}` triple `GET /kinds/select` returns. */
export interface WarrantyKindRef {
  id: string;
  code: string;
  name: string;
}

// ── Policies ────────────────────────────────────────────────────────────────

export interface WarrantyPolicyRow {
  id: string;
  version: string;
  /** ISO `YYYY-MM-DD`. Never a datetime - a policy window is a civil day. */
  effective_from: string;
  /** `null` = open ended (still in force). */
  effective_to: string | null;
  policy_text: string | null;
  /** Resolved filename of `source_attachment_id`; the id itself is never rendered. */
  source_attachment_name: string | null;
  /** Drives the AC-P13 delete confirmation. */
  term_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface WarrantyPolicyWrite {
  version: string;
  effective_from: string;
  effective_to: string | null;
  policy_text: string | null;
}

/**
 * AC-P14: policies use `ListResponse[T]` -
 * `{data, pagination:{total, page, limit}, empty}` - which IS the frontend's own
 * `DataGridApiResponse<T>`. Reused rather than redeclared, so a `{data, total}`
 * shape cannot creep back in. Kinds, kinds-select, kind-rules and defect-types
 * are bare arrays.
 */
export type WarrantyPolicyPage = DataGridApiResponse<WarrantyPolicyRow>;

/** `POST /policies/{id}/supersede` - one transaction, two rows (AC-P2a). */
export interface SupersedeResult {
  closed: WarrantyPolicyRow;
  created: WarrantyPolicyRow;
}

// ── Terms ───────────────────────────────────────────────────────────────────

export interface WarrantyTermRow {
  id: string;
  policy_id: string;
  kind_id: string;
  kind_code: string;
  kind_name: string;
  part_name: string;
  /** Mutually exclusive with `is_lifetime` (AC-P3a). */
  duration_months: number | null;
  is_lifetime: boolean;
  /** `lookup_options.id` values. NULL and [] both mean EVERY defect. */
  covered_defect_type_ids: string[] | null;
  /** Resolved labels for the above, so the screen never prints a uuid. */
  covered_defect_type_labels: string[] | null;
  installation_included: boolean;
  registration_bonus_months: number | null;
  qualifications: string | null;
  exclusions: string | null;
  /** Drives the AC-P8a delete confirmation. Assessments survive the delete. */
  assessment_count: number;
}

export interface WarrantyTermWrite {
  kind_id: string;
  part_name: string;
  duration_months: number | null;
  is_lifetime: boolean;
  covered_defect_type_ids: string[] | null;
  installation_included: boolean;
  registration_bonus_months: number | null;
  qualifications: string | null;
  exclusions: string | null;
}

/** `GET /policies/{pid}/terms?group_by=kind` (AC-P4). */
export interface WarrantyTermKindGroup {
  kind: WarrantyKindRef;
  terms: WarrantyTermRow[];
}

export interface WarrantyTermsGrouped {
  groups: WarrantyTermKindGroup[];
  total: number;
}

// ── Kinds ───────────────────────────────────────────────────────────────────

export interface WarrantyKindRow {
  id: string;
  code: string;
  name: string;
  consumer_label: string | null;
  consumer_icon: string | null;
  sort_order: number;
  is_active: boolean;
  /** Zero = no product can ever reach this Kind (AC-P7). */
  rule_count: number;
  /** Zero = every product that reaches it returns `no_term` (AC-P7a). */
  term_count: number;
  /**
   * AC-P17: the zero is a SERVER-SIDE fact, not a grid-cell comparison. A flag
   * computed in a cell is visible in exactly one place and invisible to export,
   * to MCP and to the AI assistant - AC-P7's own disease one layer up. The grid
   * renders from these, never from `rule_count === 0`.
   */
  has_no_rules: boolean;
  has_no_terms: boolean;
}

export interface WarrantyKindWrite {
  code: string;
  name: string;
  consumer_label: string | null;
  consumer_icon: string | null;
  sort_order: number;
  is_active: boolean;
}

// ── Kind rules ──────────────────────────────────────────────────────────────

export interface WarrantyKindRuleRow {
  id: string;
  kind_id: string;
  kind_code: string;
  kind_name: string;
  match_type: KindRuleMatchType;
  match_value: string;
  /** Higher wins, consulted BEFORE match-type specificity (AC-D20). */
  priority: number;
}

export interface WarrantyKindRuleWrite {
  kind_id: string;
  match_type: KindRuleMatchType;
  match_value: string;
  priority: number;
}

/**
 * The EDIT body. `KindRuleUpdate` is all-Optional server-side, and AC-P24 is
 * "strict at write, tolerant at read": a row may already hold a `match_type`
 * outside the four the frontend knows. Sending the field back on every PATCH
 * would rewrite that stored value from a picker the admin never touched - so
 * `match_type` is omitted entirely unless the admin actually chose one, and the
 * untouched legacy row survives an edit to its other fields.
 *
 * Create stays STRICT: `WarrantyKindRuleWrite` still requires the field.
 */
export type WarrantyKindRuleUpdate = Omit<WarrantyKindRuleWrite, 'match_type'> &
  Partial<Pick<WarrantyKindRuleWrite, 'match_type'>>;

// ── The tester (AC-P6, P6b, P6c) ────────────────────────────────────────────

/** An unsaved rule the admin is about to write, ranked alongside the saved ones. */
export interface CandidateKindRule {
  kind_id: string;
  match_type: KindRuleMatchType;
  match_value: string;
  priority: number;
}

export interface KindRuleTestRequest {
  product_code: string | null;
  category_code: string | null;
  product_name: string | null;
  candidate_rule: CandidateKindRule | null;
}

/** `id` is null for the unsaved candidate - it has not been written yet. */
export interface TestedRule {
  id: string | null;
  kind_id: string;
  match_type: KindRuleMatchType;
  match_value: string;
  priority: number;
  is_candidate: boolean;
}

export interface KindRuleTestMatch {
  rank: number;
  rule: TestedRule;
  kind: WarrantyKindRef;
  matched_length: number;
  is_candidate: boolean;
}

export interface KindRuleTestResponse {
  /** null = no rule reached any Kind, so no verdict is possible for this product. */
  resolved_kind: WarrantyKindRef | null;
  /** `matches[0]`, or null. */
  deciding_rule: TestedRule | null;
  matches: KindRuleTestMatch[];
}

// ── Defect types (the picker behind `covered_defect_type_ids`) ──────────────

export interface DefectTypeOption {
  id: string;
  label: string;
}
