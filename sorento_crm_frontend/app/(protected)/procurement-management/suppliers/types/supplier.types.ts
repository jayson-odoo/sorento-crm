export interface Supplier {
  id: string;
  supplier_code: string;
  supplier_name: string;
  contact_name?: string | null;
  email?: string | null;
  phone_number?: string | null;
  website?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  payment_terms_days: number;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  updated_by?: string | null;
}

export interface SupplierFormData {
  supplier_code: string;
  supplier_name: string;
  contact_name?: string;
  email?: string;
  phone_number?: string;
  website?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
  payment_terms_days: number;
  is_active: boolean;
}

export interface SupplierDetail extends Supplier {
  linked_products_count?: number;
  performance_rating?: {
    on_time_delivery: number;
    quality: number;
    price_competitiveness: number;
    overall: number;
  };
  recent_orders?: any[];
  attachments?: any[];
}
