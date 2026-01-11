import type { Product, Supplier } from '../../products/types/product.types';

export interface ProductSupplier {
  id: string;
  product_id: string;
  supplier_id: string;
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
}
