/**
 * A country, referenced by a supplier's Country field today and by a customer or user's
 * later (`PLAN-local-supplier-oi-routing.md`).
 *
 * API contract: `/api/v1/master-data/countries` (list / select / get / post / put / delete).
 */
export interface Country {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CountryFormData {
  code: string;
  name: string;
  is_active: boolean;
}

/** One country as a `SearchableSelect` option source - active rows only. */
export interface CountrySelectItem {
  id: string;
  code: string;
  name: string;
}
