/**
 * Shared fixtures for the Costing page tests (lane PRODUCT-COSTING, Phase 2 red tests).
 * Shapes are CONTRACT-product-costing.md section 4.1 (Row, Party, response envelope), with the
 * owner's workbook figures: WB 245 / CGB9032B, RMB 34.50, rate 1.6, SST 1.10, + RM 8, landing
 * 31.71875, Bath Plus (304-R017) at 8% -> final 34.25625, margin 130.61%.
 */

export const PARTY = {
  customer_id: 'cust-1',
  customer_code: '304-R017',
  customer_name: 'RELATED - BATHPLUS SDN BHD',
  has_profile: true,
  markup_pct: 8,
  cost_method: null,
  is_active: true,
  product_count: 8,
};

type Dict = Record<string, unknown>;

const BASE: Dict = {
  product_id: 'p-wb245',
  product_code: 'CGB9032B',
  product_name: 'WB 245 Basin',
  category_id: 'cat-ceramics',
  category_name: 'Ceramics',
  brand_id: 'b1',
  brand_name: 'Mocha',
  list_price: 79,
  supplier_id: 's-a',
  supplier_code: 'SUP-A01',
  currency: 'RMB',
  unit_cost: 34.5,
  rate_to_base: 0.625,
  units_per_base: 1.6,
  rate_effective_from: '2026-11-01',
  sst_factor: 1.1,
  transport_mode: 'add',
  transport_value: 8,
  transport_source: 'category',
  landing: 31.71875,
  cost_method: 'primary',
  cost_method_source: 'company',
  cost_method_supplier_id: null,
  markup_pct: 8,
  markup_source: 'party',
  final: 34.25625,
  margin_pct: 130.61,
  po_number: null,
  po_date: null,
  reasons: [],
  skipped: [],
  party_product_id: 'cpp-1',
};

export function costingRow(over: Dict = {}): Dict {
  return { ...BASE, ...over };
}

/** WB 245 in the party view: everything inherited, so no "Set on this row" marker. */
export const WB245 = costingRow();

/** Jacuzzi at a row mark-up of 10%: 1692.375 -> 1861.6125. Mark-up is set on the row. */
export const JACUZZI = costingRow({
  product_id: 'p-jz',
  product_code: 'JZ-1xx',
  product_name: 'Jacuzzi (masked)',
  category_id: 'cat-jacuzzi',
  category_name: 'Jacuzzi',
  list_price: 3999,
  supplier_id: 's-j',
  supplier_code: 'SUP-J02',
  unit_cost: 2450,
  landing: 1692.375,
  markup_pct: 10,
  markup_source: 'row',
  final: 1861.6125,
  margin_pct: 114.81,
  party_product_id: 'cpp-2',
});

/** An accessory with no cost anywhere: every derived figure is null, reason no_cost. */
export const ACCESSORY = costingRow({
  product_id: 'p-acc',
  product_code: 'A-4xx',
  product_name: 'Accessory (masked)',
  category_id: 'cat-acc',
  category_name: 'Accessories',
  list_price: 12,
  supplier_id: null,
  supplier_code: null,
  currency: null,
  unit_cost: null,
  rate_to_base: null,
  units_per_base: null,
  rate_effective_from: null,
  landing: null,
  final: null,
  margin_pct: null,
  reasons: [{ code: 'no_cost' }],
  party_product_id: 'cpp-3',
});

export const NO_RATE = costingRow({
  product_id: 'p-eur',
  product_code: 'E-5xx',
  product_name: 'Euro priced',
  currency: 'EUR',
  unit_cost: 20,
  rate_to_base: null,
  units_per_base: null,
  landing: null,
  final: null,
  margin_pct: null,
  reasons: [{ code: 'no_rate', currency: 'EUR', date: '2026-11-11' }],
  party_product_id: 'cpp-4',
});

export const NO_PRIMARY = costingRow({
  product_id: 'p-np',
  product_code: 'N-6xx',
  product_name: 'No primary',
  supplier_id: null,
  supplier_code: null,
  currency: null,
  unit_cost: null,
  landing: null,
  final: null,
  margin_pct: null,
  reasons: [{ code: 'no_primary' }],
  party_product_id: 'cpp-5',
});

export const NO_TRANSPORT = costingRow({
  product_id: 'p-nt',
  product_code: 'T-7xx',
  product_name: 'No transport rule',
  transport_mode: null,
  transport_value: null,
  transport_source: null,
  reasons: [{ code: 'no_transport_rule' }],
  party_product_id: 'cpp-6',
});

export function partyEnvelope(rows: Dict[] = [WB245, JACUZZI, ACCESSORY], over: Dict = {}) {
  return {
    data: rows,
    total: rows.length,
    page: 1,
    limit: 50,
    as_of: '2026-11-11',
    view: 'party',
    party: PARTY,
    settings: { sst_factor: 1.1, default_method: 'primary' },
    ...over,
  };
}

/** Company standard: Final = list price, Mark-up = achieved, no Margin. WB 245 achieved 149.06%. */
export function standardEnvelope(rows?: Dict[], over: Dict = {}) {
  const standardRows = rows ?? [
    costingRow({ markup_pct: 149.06, markup_source: 'achieved', final: 79, margin_pct: null, party_product_id: null }),
    costingRow({
      product_id: 'p-jz', product_code: 'JZ-1xx', product_name: 'Jacuzzi (masked)', category_name: 'Jacuzzi',
      list_price: 3999, landing: 1692.375, markup_pct: 136.3, markup_source: 'achieved', final: 3999,
      margin_pct: null, party_product_id: null,
    }),
    costingRow({
      product_id: 'p-acc', product_code: 'A-4xx', product_name: 'Accessory (masked)', category_name: 'Accessories',
      supplier_id: null, supplier_code: null, currency: null, unit_cost: null, rate_to_base: null,
      units_per_base: null, landing: null, markup_pct: null, markup_source: 'achieved', final: 12,
      margin_pct: null, reasons: [{ code: 'no_cost' }], party_product_id: null,
    }),
  ];
  return {
    data: standardRows,
    total: standardRows.length,
    page: 1,
    limit: 50,
    as_of: '2026-11-11',
    view: 'standard',
    party: null,
    settings: { sst_factor: 1.1, default_method: 'primary' },
    ...over,
  };
}

export const SUPPLIERS = {
  data: [
    { supplier_id: 's-a', supplier_code: 'SUP-A01', supplier_name: 'Supplier A', is_primary: true, lead_time_days: 45, currency: 'RMB', unit_cost: 34.5, landing: 31.71875, final: 34.25625, markup_pct: 8, margin_pct: 130.61, reasons: [] },
    { supplier_id: 's-b', supplier_code: 'SUP-B07', supplier_name: 'Supplier B', is_primary: false, lead_time_days: 60, currency: 'RMB', unit_cost: 38, landing: 34.125, final: 36.855, markup_pct: 8, margin_pct: 114.35, reasons: [] },
    { supplier_id: 's-l', supplier_code: 'SUP-L02', supplier_name: 'Supplier L', is_primary: false, lead_time_days: 7, currency: 'MYR', unit_cost: 42, landing: 54.2, final: 58.536, markup_pct: 8, margin_pct: 34.96, reasons: [] },
  ],
};
