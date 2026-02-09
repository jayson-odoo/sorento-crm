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
  created_time?: Date | null;
  debtor_code?: string | null;
  debtor_name?: string | null;
  agent?: string | null;
  is_cancelled?: boolean | null;
  remarks_cs?: string | null;
  order_type?: string | null;
  delivery_time?: string | null;
  checker?: string | null;
  transporter?: string | null;
  driver_name?: string | null;
  lorry_plate?: string | null;
  customer_ref?: string | null;
  delivery_remarks_cs?: string | null;
  delivery_remarks?: string | null;
  salesman?: string | null;
  trips?: number | null;
  warehouse?: string | null;
  delivery_days?: number | null;
  kpi_warning?: boolean | null;
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
  customer_id?: string | null;
  order_status_id: string;
  billing_address_id?: string;
  shipping_address_id?: string;
  created_time?: Date;
  debtor_code?: string;
  debtor_name?: string;
  agent?: string;
  is_cancelled?: boolean;
  remarks_cs?: string;
  order_type?: string;
  delivery_time?: string;
  checker?: string;
  transporter?: string;
  driver_name?: string;
  lorry_plate?: string;
  customer_ref?: string;
  delivery_remarks_cs?: string;
  delivery_remarks?: string;
  salesman?: string;
  trips?: number;
  warehouse?: string;
  delivery_days?: number;
  kpi_warning?: boolean;
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
