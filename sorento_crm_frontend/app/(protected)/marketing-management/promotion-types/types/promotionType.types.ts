/**
 * A kind of promotion, and the rule for what happens to it after its end date.
 *
 * API contract: `/api/v1/marketing/promotion-types` (list / get / post / put / delete).
 */
export interface PromotionType {
  id: string;
  type_code: string;
  type_name: string;
  description?: string | null;
  /** Whether an expired promotion of this type may still be served to a customer. */
  show_expired: boolean;
  /** Bound: usable only while the calendar year it ended in is still running. */
  expired_valid_until_year_end: boolean;
  /** Bound: usable only while it ended within this many days. Null = no age cap. */
  expired_max_age_days?: number | null;
  /** Lowercase wording markers matched against an uploaded file's name. */
  match_markers: string[];
  /** Ascending; the first matching type wins, so the conservative type sits lowest. */
  match_priority: number;
  /** Exactly one type: the policy for a promotion with no type at all. */
  is_default: boolean;
  sort_order: number;
  promotions_count?: number;
  created_at: string;
  updated_at: string;
}

export interface PromotionTypeFormData {
  type_code: string;
  type_name: string;
  description?: string | null;
  show_expired: boolean;
  expired_valid_until_year_end: boolean;
  expired_max_age_days?: number | null;
  match_markers: string[];
  match_priority: number;
  is_default: boolean;
  sort_order: number;
}
