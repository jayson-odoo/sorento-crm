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
  orders_count?: number;
  // Extended profile (added by commercial_core)
  registered_name?: string | null;
  trading_name?: string | null;
  registration_number?: string | null;
  industry?: string | null;
  website?: string | null;
  billing_address?: Record<string, unknown> | null;
  country?: string | null;
  tax_id?: string | null;
  notes?: string | null;
  account_owner_user_id?: string | null;
  customer_type?: string | null;
  salutation?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  mobile_number?: string | null;
}

export interface CustomerFormData {
  customer_code: string;
  customer_name: string;
  email?: string;
  phone_number?: string;
  is_active: boolean;
  // Extended profile fields
  registered_name?: string;
  trading_name?: string;
  registration_number?: string;
  industry?: string;
  website?: string;
  billing_address?: Record<string, unknown> | null;
  country?: string;
  tax_id?: string;
  notes?: string;
  account_owner_user_id?: string;
  customer_type?: string;
  salutation?: string;
  first_name?: string;
  last_name?: string;
  mobile_number?: string;
}

export interface CustomerDetail extends Customer {
  orders_count?: number;
}
