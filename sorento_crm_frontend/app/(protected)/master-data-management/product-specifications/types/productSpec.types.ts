export interface SpecValue {
  value: string | number | boolean;
  unit?: string;
}

export interface SpecProvenance {
  /** derived | rule | human. `human` survives re-derivation. */
  source: string;
  confidence: number;
  /** The exact substring the value was read from. */
  evidence: string;
}

export interface ProductSpecRow {
  product_id: string;
  product_code: string;
  class_label: string | null;
  brand_hint: string | null;
  spec_count: number;
  /** The code-free sentence that gets embedded. This is what search matches. */
  rendered_text: string | null;
  status: string;
  is_accessory: boolean;
  is_discontinued: boolean;
  open_exceptions: number;
  values: Record<string, SpecValue>;
  provenance: Record<string, SpecProvenance>;
}

export interface SpecException {
  id: string;
  /** Absent when the exception is already scoped to one product. */
  product_code?: string;
  spec_key: string;
  /** shape_mismatch | column_conflict | implausible_dimension */
  reason: string;
  proposed: Record<string, unknown> | null;
  stored: Record<string, unknown> | null;
}

/**
 * Why a product has no derived specs. Reported instead of a blank, because the four
 * silences have four different fixes and only one of them lives in the ranker.
 */
export type SpecDiagnosisReason =
  | 'eligible'
  | 'not_yet_derived'
  | 'class_not_enabled'
  | 'category_non_searchable'
  | 'code_unparsed'
  | 'no_category';

export interface ProductSpecDetail {
  product_id: string;
  product_code: string;
  category_code: string | null;
  /** True only when a spec row exists — i.e. the chatbot can actually find this. */
  searchable: boolean;
  diagnosis: {
    reason: SpecDiagnosisReason;
    class_label: string | null;
    brand_hint: string | null;
    suffix: string | null;
  };
  spec: {
    values: Record<string, SpecValue>;
    provenance: Record<string, SpecProvenance>;
    rendered_text: string | null;
    status: string;
    derived_at: string | null;
  } | null;
  exceptions: SpecException[];
  /** The description the derivation read. Shown so a wrong value can be traced. */
  source_text: string;
}

export interface SpecCandidate {
  product_id: string;
  product_code: string;
  summary: string;
  class: string | null;
  matched_specs: string[];
  score: number;
  is_discontinued: boolean;
  is_accessory: boolean;
}

export interface SpecPreviewResult {
  candidates: SpecCandidate[];
  /** True when nothing cleared the floor: the bot would ask for a code instead. */
  floor_missed: boolean;
  top_score: number;
  floor: number;
}

export interface SpecRegistryKey {
  spec_key: string;
  label: string;
  data_type: string;
  unit: string | null;
  allowed_values: string[];
  synonyms: Record<string, string[]>;
  applies_when: Record<string, string[]>;
  rank_weight: number | null;
  measured_coverage: number | null;
}
