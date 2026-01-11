export interface Stock {
  id: string;
  product_id: string;
  warehouse_id: string;
  quantity: number;
  reserved_quantity: number;
  uom_id: string;
  created_at: Date;
  updated_at: Date;
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
  available?: number; // quantity - reserved_quantity
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
