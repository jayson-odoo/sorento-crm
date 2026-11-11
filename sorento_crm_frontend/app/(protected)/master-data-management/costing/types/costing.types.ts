/**
 * Products > Costing (lane PRODUCT-COSTING). Shapes are
 * documentation/plans/products/CONTRACT-product-costing.md section 4, as the backend serves them.
 * Money and rates are numbers (6 dp from the API); an unknown value is `null`, never 0.
 */

export type CostMethod = 'primary' | 'selected' | 'average' | 'last_po';
export type TransportMode = 'add' | 'multiply';
export type MarkupSource = 'row' | 'party' | 'achieved';
export type Source = 'product' | 'category' | 'party' | 'company';

export type ReasonCode =
  | 'no_cost'
  | 'no_rate'
  | 'no_primary'
  | 'selected_not_linked'
  | 'no_po_price'
  | 'no_transport_rule'
  | 'no_list_price';

export interface CostingReason {
  code: ReasonCode;
  /** no_rate only. */
  currency?: string;
  /** no_rate only: the day the rate was looked up for, YYYY-MM-DD. */
  date?: string;
}

export interface SkippedSupplier {
  supplier_code: string | null;
  reason: string;
}

export interface CostingRow {
  product_id: string;
  product_code: string;
  product_name: string;
  category_id: string | null;
  category_name: string | null;
  brand_id: string | null;
  brand_name: string | null;
  list_price: number | null;
  supplier_id: string | null;
  supplier_code: string | null;
  supplier_name: string | null;
  currency: string | null;
  unit_cost: number | null;
  rate_to_base: number | null;
  units_per_base: number | null;
  rate_effective_from: string | null;
  sst_factor: number;
  transport_mode: TransportMode | null;
  transport_value: number | null;
  transport_source: 'product' | 'category' | null;
  /** The product's own category rule, whatever the source; null when it has none. */
  category_transport_mode: TransportMode | null;
  category_transport_value: number | null;
  landing: number | null;
  cost_method: CostMethod;
  cost_method_source: 'product' | 'party' | 'company';
  cost_method_supplier_id: string | null;
  markup_pct: number | null;
  markup_source: MarkupSource;
  final: number | null;
  margin_pct: number | null;
  po_number: string | null;
  po_date: string | null;
  reasons: CostingReason[];
  skipped: SkippedSupplier[];
  party_product_id: string | null;
}

export interface CostingParty {
  customer_id: string;
  customer_code: string;
  customer_name: string;
  has_profile: boolean;
  markup_pct: number | null;
  cost_method: Exclude<CostMethod, 'selected'> | null;
  is_active: boolean | null;
  product_count: number;
}

export interface CostingSettings {
  sst_factor: number;
  default_method: Exclude<CostMethod, 'selected'>;
}

export interface CostingRowsResponse {
  data: CostingRow[];
  total: number;
  page: number;
  limit: number;
  as_of: string;
  view: 'standard' | 'party';
  party: CostingParty | null;
  settings: CostingSettings;
}

/** The query names the API takes (GET /rows and GET /export). */
export interface CostingRowsParams {
  party_id?: string;
  /** Search text (code or name). */
  query?: string;
  category_id?: string;
  brand_id?: string;
  cost_method?: string;
  /** Sent only when true; absent means no narrowing. */
  has_cost?: boolean;
  as_of?: string;
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
}

export interface CostingSupplierParams {
  party_id?: string;
  as_of?: string;
}

export interface SupplierBreakdown {
  supplier_id: string;
  supplier_code: string;
  supplier_name: string;
  is_primary: boolean;
  lead_time_days: number | null;
  currency: string | null;
  unit_cost: number | null;
  landing: number | null;
  final: number | null;
  markup_pct: number | null;
  margin_pct: number | null;
  reasons: CostingReason[];
}

export interface HistoryEntry {
  changed_at: string;
  user_name: string;
  field: string;
  old: string | number | null;
  new: string | number | null;
}

/** One product's changed cells. Only keys present are changed; null clears. */
export interface RowChange {
  product_id: string;
  markup_pct?: number | null;
  transport_mode?: TransportMode | null;
  transport_value?: number | null;
  cost_method?: CostMethod | null;
  cost_method_supplier_id?: string | null;
}

export interface SaveRowsBody {
  party_id: string | null;
  changes: RowChange[];
}

export interface CategoryRule {
  category_id: string;
  category_name: string;
  mode: TransportMode | null;
  value: number | null;
}

export interface ExchangeRate {
  id: string;
  currency: string;
  rate_to_base: number;
  units_per_base: number | null;
  effective_from: string;
  note: string | null;
  status: 'scheduled' | 'in_force' | 'past';
}

/** Exactly one of the two rate fields. */
export interface ExchangeRateBody {
  currency?: string;
  effective_from?: string;
  rate_to_base?: number;
  units_per_base?: number;
  note?: string;
}

export interface PartyBody {
  markup_pct: number;
  cost_method: Exclude<CostMethod, 'selected'> | null;
  is_active: boolean;
}
