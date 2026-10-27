/** `GET /api/v1/inventory/stock-position` (PLAN-stock-position-report-27oct). */
export interface StockPositionRow {
  product_id: string;
  item_code: string;
  description: string | null;
  supplier_id: string | null;
  supplier_code: string | null;
  supplier_name: string | null;
  brand_id: string | null;
  brand_name: string | null;
  /** On hand per site-pool warehouse code; a warehouse the item has nothing in is absent. */
  stock: Record<string, number>;
  incoming_pool: number;
  total_stock: number;
  incoming_project: number;
  total_incoming: number;
  packing_list_open: number;
  /** Dealer SO still owed, negative as the supplier sheet prints it. */
  outstanding_dealer: number;
  outstanding_po: number;
  monthly_sales: number;
  highest_month: number;
}

export interface StockPositionResponse {
  data: StockPositionRow[];
  /** The warehouse columns: active site-pool warehouses holding stock, by code. */
  warehouses: { id: string; code: string }[];
  pagination: { page: number; limit: number; total: number; total_pages: number };
}

export interface StockPositionFilters {
  supplierId?: string;
  brandId?: string;
  warehouseId?: string;
}
