export interface StockBatch {
  id: string;
  product_id: string;
  batch_code: string;
  quantity: number;
  manufactured_date?: Date | null;
  expiry_date?: Date | null;
  received_date: Date;
  warehouse_id: string;
  storage_zone_id?: string | null;
  status: 'available' | 'reserved' | 'damaged' | 'expired' | 'returned';
  created_at: Date;
  updated_at: Date;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  warehouse?: {
    id: string;
    warehouse_name: string;
  };
  storage_zone?: {
    id: string;
    zone_name: string;
  };
  serial_numbers?: SerialNumber[];
}

export interface SerialNumber {
  id: string;
  batch_id: string;
  serial_number: string;
  status: string;
  qr_code?: string | null;
  created_at: Date;
}

export interface BatchFormData {
  product_id: string;
  batch_code: string;
  quantity: number;
  manufactured_date?: Date | null;
  expiry_date?: Date | null;
  received_date: Date;
  warehouse_id: string;
  storage_zone_id?: string;
  status: 'available' | 'reserved' | 'damaged' | 'expired' | 'returned';
  serial_numbers?: string[];
}
