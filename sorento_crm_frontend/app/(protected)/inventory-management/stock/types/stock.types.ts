export interface Stock {
  id: string;
  product_id: string;
  warehouse_id: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  quantity_damaged?: number;
  zone_id?: string | null;
  reorder_point?: number | null;
  created_at: Date;
  updated_at?: Date | null;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
    reorder_level: number;
    category?: { category_name: string };
  };
  warehouse?: {
    id: string;
    warehouse_name: string;
  };
  // Legacy fields for backward compatibility
  quantity?: number; // Maps to quantity_on_hand
  reserved_quantity?: number; // Maps to quantity_reserved
  available?: number; // Maps to quantity_available
  status?: 'low' | 'critical' | 'normal' | 'overstock';
}

export interface StockDashboard {
  total_skus: number;
  total_quantity: number;
  low_stock_alert_count: number;
  overstock_warning_count: number;
  stock_by_warehouse: Array<{ warehouse_id: string; warehouse_name: string; total_quantity: number }>;
  stock_by_category: Array<{ category_name: string; total_quantity: number }>;
  stock_movement_30_days: Array<{ date: string; quantity: number }>;
  low_stock_alerts: Array<{
    product_code: string;
    product_name: string;
    warehouse_name: string;
    quantity: number;
    reorder_level: number;
  }>;
}
