export interface Warehouse {
  id: string;
  warehouse_code: string;
  warehouse_name: string | null;
  location: string | null;
  manager_id?: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date | null;
  zones_count?: number;
  /** Whether stock here may cover demand in the reorder plan. */
  counts_as_available?: boolean;
  /** The shared pool this location draws on; null means it is its own pool. */
  pool_warehouse_id?: string | null;
  /** Resolved for display, so no UUID is ever rendered. */
  pool_warehouse_code?: string | null;
  /** Who this location sells to: dealer or project. Splits cost, price and history. */
  segment?: string | null;
}

export interface WarehouseFormData {
  warehouse_code: string;
  warehouse_name?: string | null;
  location?: string | null;
  manager_id?: string | null;
  is_active: boolean;
  counts_as_available?: boolean;
  pool_warehouse_id?: string | null;
  segment?: string | null;
}
