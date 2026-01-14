export interface Order {
  id: string;
  order_number: string;
  order_date?: Date | null;
  promised_delivery_date?: Date | null;
  actual_delivery_date?: Date | null;
  customer_id?: string | null;
  order_status_id?: string | null;
  created_by?: string | null;
  updated_by?: string | null;
  billing_address_id?: string | null;
  shipping_address_id?: string | null;
  subtotal_amount: number;
  discount_amount: number;
  tax_amount: number;
  total_amount: number;
  remarks?: string | null;
  created_at: Date;
  updated_at: Date;
  deleted_at?: Date | null;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  customer?: {
    id: string;
    customer_code: string;
    customer_name: string;
  };
  order_status?: {
    id: string;
    status_code: string;
    status_name: string;
  };
}

export interface OrderFormData {
  order_number: string;
  order_date: Date;
  promised_delivery_date?: Date;
  actual_delivery_date?: Date;
  customer_id: string;
  order_status_id: string;
  billing_address_id?: string;
  shipping_address_id?: string;
  subtotal_amount: number;
  discount_amount?: number;
  tax_amount?: number;
  total_amount: number;
  remarks?: string;
}

export interface OrderDetail extends Order {
  customer?: {
    id: string;
    customer_code: string;
    customer_name: string;
    contact_name?: string | null;
    email?: string | null;
    phone_number?: string | null;
  };
  order_status?: {
    id: string;
    status_code: string;
    status_name: string;
    description?: string | null;
  };
}
