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
}

export interface WarehouseFormData {
  warehouse_code: string;
  warehouse_name?: string | null;
  location?: string | null;
  manager_id?: string | null;
  is_active: boolean;
}
