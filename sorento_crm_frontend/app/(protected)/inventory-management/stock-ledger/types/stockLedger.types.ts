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
  created_by_name?: string | null;
  created_at: Date;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  warehouse?: {
    id: string;
    warehouse_name: string;
  };
}

/** Every `transaction_type` the backend writes, as the Type filter offers them. */
export const STOCK_LEDGER_TRANSACTION_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'AUTOCOUNT_PUSH', label: 'AutoCount push' },
  { value: 'BULK_IMPORT', label: 'Bulk import' },
  { value: 'SYSTEM_ADJUSTMENT', label: 'System adjustment' },
];

const TYPE_LABELS = new Map(STOCK_LEDGER_TRANSACTION_TYPE_OPTIONS.map((o) => [o.value, o.label]));

/** The label for a `transaction_type`; an unknown code reads as itself. */
export function stockLedgerTypeLabel(type: string): string {
  return TYPE_LABELS.get(type) ?? type;
}
