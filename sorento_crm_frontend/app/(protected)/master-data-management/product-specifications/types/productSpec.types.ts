import type { VerificationBlock } from '../../spec-verification/types/specVerification.types';

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
  /** True only when a spec row exists - i.e. the chatbot can actually find this. */
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
  /**
   * Who vouched for this code and when, derived server-side (AC-D.2). Carried on this
   * response rather than fetched separately, so the tab costs no second round trip and
   * both company copies of a code read the same badge (AC-D.14).
   */
  verification: VerificationBlock;
  /**
   * The hash of the values on screen. Echoed back on verify, so a code whose values
   * moved while it was being reviewed is refused rather than silently stamped (AC-D.4).
   */
  values_hash: string;
}

export interface SpecCandidate {
  product_id: string;
  product_code: string;
  summary: string;
  class: string | null;
  matched_specs: string[];
  score: number;
  is_discontinued: boolean;
}

/** A spec the customer asked for that nothing offered can satisfy. */
export interface UnmetSpec {
  key: string;
  value: string | number | boolean;
}

export interface SpecPreviewResult {
  candidates: SpecCandidate[];
  /** True when nothing cleared the floor: the bot would ask for a code instead. */
  floor_missed: boolean;
  top_score: number;
  floor: number;
  /** Null when the caller passed structured specs rather than a raw phrase. */
  understanding: SpecUnderstanding | null;
  unmet: UnmetSpec[];
}

/**
 * A rule row's sentence form. The engine never reads this - it is compiled to
 * `match` / `pattern` / `capture` / `value` (see `compileBuilder` in `lib/ruleSentence.ts`)
 * and that compiled form is what actually runs. Present only on rows built from the
 * kind menu; a row edited into a pattern (Advanced -> Edit pattern) drops it.
 */
export type SpecRuleBuilderKind =
  | 'number_after'
  | 'number_before'
  | 'number_between'
  | 'text_contains'
  | 'text_ends_with'
  | 'word_present'
  | 'code_contains'
  | 'code_starts_with'
  | 'code_ends_with'
  | 'from_field'
  | 'size_triple'
  | 'name_head';

export interface SpecRuleBuilder {
  kind: SpecRuleBuilderKind;
  /** number_after / number_before: the word. text_contains / text_ends_with / word_present
   *  / code_*: the phrase or token. */
  word?: string;
  /** number_between only: the two phrases it reads between. */
  from?: string;
  to?: string;
  /** text_contains / text_ends_with / code_*: what the key is set to when it matches. */
  value?: string | number | boolean;
  /** size_triple only: 1 = length, 2 = width, 3 = height, 4 = thickness. */
  position?: number;
  /** from_field only: category | brand | column:<products column>. */
  field?: string;
}

/** One way of reading a value out of a product's text. */
export interface SpecDerivationRule {
  /** contains | ends_with | present | regex | code_contains | code_starts_with | code_suffix
   *  | from_field. The compiled form - always kept in sync with `builder` when one is set. */
  match: string;
  pattern: string;
  value?: string | number | boolean;
  capture?: number;
  /** Limit the rule to one text: description | flyer. Absent means both. */
  source?: string;
  /** The sentence this row was built from, when it was built that way. */
  builder?: SpecRuleBuilder;
  /** This row ships with the product; a small tag says so. Still an ordinary row -
   *  draggable, editable, removable. */
  shipped?: boolean;
  /** A shipped row a migration prepended so an owned key kept the reader it used to
   *  run silently. Renders the same `shipped` tag as `shipped`. */
  shipped_backfill?: boolean;
  /**
   * Browser-only identity, so dragging a rule moves THAT RULE rather than that
   * position. Not persisted: the API builds each stored rule from the fields it knows
   * and drops everything else.
   */
  _uid?: string;
}

/** One row's try-it read, aligned to `rules` by index. */
export interface SpecTryRuleRead {
  index: number;
  value: string | number | boolean | null;
  /** The exact text the value was read from, or null when nothing matched. */
  evidence: string | null;
}

/** What trying the draft rules against one product or one pasted text answers. */
export interface SpecTryResult {
  description: string;
  reads: SpecTryRuleRead[];
  /** The first row with a value, i.e. the one the engine would keep. Null when none matched. */
  winner_index: number | null;
}

/** One row of the preview's before/after sample. */
export interface SpecPreviewSampleRow {
  code: string;
  before: string | number | boolean | null;
  after: string | number | boolean | null;
}

/** What `GET .../preview/{jobId}` answers, pending or done. */
export interface SpecPreviewJobResult {
  status: 'pending' | 'done';
  changed?: number;
  added?: number;
  removed?: number;
  unchanged?: number;
  sample?: SpecPreviewSampleRow[];
}

export interface SpecRegistryKey {
  spec_key: string;
  label: string;
  data_type: string;
  unit: string | null;
  allowed_values: string[];
  /**
   * Values the catalog holds but nobody searches for - the placeholder brands OTHERS
   * and NO LOGO, which record the absence of a brand. Excluded ones are hidden from
   * the understanding model, which was otherwise filing every word it could not place
   * under one.
   */
  excluded_values: string[];
  /** Values staff added to a shipped key - the removable half of `allowed_values`. */
  user_values: string[];
  /** Shipped values this business has taken away. Already subtracted from `allowed_values`. */
  suppressed_values: string[];
  /**
   * A standing preference for particular values of this key ({ SORENTO: 1.5 }) -
   * applied to any product carrying the value, except when the customer named the key
   * themselves.
   */
  value_weights: Record<string, number>;
  /** How this key is read out of a product's text. First match wins, so order matters. */
  derivation_rules: SpecDerivationRule[];
  /**
   * The rules that ACTUALLY run. Equal to `derivation_rules` once a key has been
   * edited; before that it is the set that ships in code, which derivation falls back
   * to - so a key with an empty column is not a key with no rules.
   */
  effective_rules: SpecDerivationRule[];
  /** True while this key is still running the shipped rules rather than its own. */
  rules_are_default: boolean;
  /** Seed + user words, already merged. What a customer can actually say. */
  synonyms: Record<string, string[]>;
  applies_when: Record<string, string[]>;
  /**
   * `rules` - filled in by the derivation rules below.
   * `measurement_then_rules` - the size in the description comes first; rules fill the
   * gap when it states none, which is how the flyer's "L680xW375xH770mm" gets in.
   * `product_record` - read off the product itself. Brand only; no rule can change it.
   */
  read_from: 'rules' | 'measurement_then_rules' | 'product_record';
  rank_weight: number | null;
  measured_coverage: number | null;
  /**
   * `seed` ships with the product and is repaired on every deploy, so its values
   * cannot be edited here - only extended. `user` keys are owned by whoever made them.
   */
  source: 'seed' | 'user';
  /** Staff-added phrasings only, i.e. the editable half of `synonyms`. */
  user_synonyms: Record<string, string[]>;
  /** Shipped words this business has taken away. Already subtracted from `synonyms`. */
  suppressed_synonyms: Record<string, string[]>;
  match_tolerance: number;
  match_decay: number;
  is_active: boolean;
  /** A number above this is dropped as implausible rather than stored. Null/absent
   *  means no cap. Seeded 5000 on mm keys; editable per key. */
  max_value?: number | null;
}

/** One tunable number in the ranker's scoring. */
export interface SpecSearchPolicyRow {
  policy_key: string;
  label: string;
  help_text: string;
  value: number;
  default_value: number;
}

/** What the phrase was understood to mean, and whether a model was involved. */
export interface SpecUnderstanding {
  source: 'semantic' | 'deterministic';
  model: string | null;
  elapsed_ms: number | null;
  specs: { key: string; value: string | number | boolean }[];
  /** What the customer RULED OUT. Products known to hold one are removed entirely. */
  exclusions: { key: string; value: string | number | boolean }[];
  free_terms: string[];
  notes: string;
}
