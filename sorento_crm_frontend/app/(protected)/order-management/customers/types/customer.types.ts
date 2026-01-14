export interface Customer {
  id: string;
  customer_code: string;
  customer_name: string;
  email?: string | null;
  phone_number?: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at?: Date | null;
  created_by?: string | null;
}

export interface CustomerFormData {
  customer_code: string;
  customer_name: string;
  email?: string;
  phone_number?: string;
  is_active: boolean;
}

export interface CustomerDetail extends Customer {
  orders_count?: number;
}
