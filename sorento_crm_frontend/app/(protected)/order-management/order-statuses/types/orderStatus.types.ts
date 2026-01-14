export interface OrderStatus {
  id: string;
  status_code: string;
  status_name: string;
  description?: string | null;
  sequence: number;
  is_final_status: boolean;
  created_at: Date;
}

export interface OrderStatusFormData {
  status_code: string;
  status_name: string;
  description?: string;
  sequence: number;
  is_final_status: boolean;
}

export interface OrderStatusDetail extends OrderStatus {
  orders_count?: number;
}
