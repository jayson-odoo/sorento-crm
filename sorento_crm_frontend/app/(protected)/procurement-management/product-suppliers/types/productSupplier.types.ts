import type { Product, Supplier } from '@/app/(protected)/master-data-management/products/types/product.types';

export interface ProductSupplier {
  id: string;
  product_id: string;
  supplier_id: string;
  standard_lead_time_days?: number;
  lead_time_days?: number;
  created_at: Date;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  supplier?: {
    id: string;
    supplier_code: string;
    supplier_name: string;
  };
}

export interface ProductSupplierFormData {
  product_id: string;
  supplier_id: string;
  standard_lead_time_days?: number;
  lead_time_days?: number;
}
