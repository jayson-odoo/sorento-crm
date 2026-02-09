export interface StorageZone {
  id: string;
  warehouse_id: string;
  zone_code: string;
  zone_name?: string | null;
  zone_type: 'shelf' | 'rack' | 'bin' | 'pallet';
  capacity: number;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  warehouse?: {
    id: string;
    warehouse_name: string;
  };
  utilization?: number;
}

export interface StorageZoneFormData {
  warehouse_id: string;
  zone_code: string;
  zone_name?: string | null;
  zone_type: 'shelf' | 'rack' | 'bin' | 'pallet';
  capacity: number;
  is_active: boolean;
}

export interface StorageZoneTreeItem extends StorageZone {
  children?: StorageZoneTreeItem[];
}
