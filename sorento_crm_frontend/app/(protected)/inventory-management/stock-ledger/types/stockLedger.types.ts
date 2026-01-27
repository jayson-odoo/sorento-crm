export interface StockLedgerEntry {
  id: string;
  product_id: string;
  warehouse_id: string;
  transaction_type: string;
  quantity_change: number;
  previous_quantity: number;
  new_quantity: number;
  reference_type?: string | null;
  reference_id?: string | null;
  notes?: string | null;
  created_by?: string | null;
  created_at: Date;
}
