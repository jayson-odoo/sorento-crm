export interface StockBalanceRun {
  id: string;
  captured_at: string;
  row_count: number;
  source: string;
  internal_note: string | null;
  follow_up: boolean;
  created_at: string;
}

export interface StockBalanceRow {
  id: string;
  item_code: string;
  product_id: string | null;
  product_name: string | null;
  location_code: string | null;
  warehouse_id: string | null;
  uom: string | null;
  batch_no: string | null;
  balance: string | number | null;
  smallest_bal_qty: string | number | null;
  standard_cost: string | number | null;
  total_cost: string | number | null;
  average_cost: string | number | null;
  rate: string | number | null;
  description: string | null;
}

export interface StockBalanceRunDetail extends StockBalanceRun {
  rows: StockBalanceRow[];
}

export interface MirrorAnnotationPayload {
  internal_note: string;
  follow_up: boolean;
}
