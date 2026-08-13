import type { Product, Supplier } from '@/app/(protected)/master-data-management/products/types/product.types';

/**
 * The terms we buy a product from one supplier ON. Every field here is read by the reorder
 * plan: the price and its currency decide whether the buy can be costed and funded at all,
 * and moq / order_multiple decide the quantity it rounds to. A blank price is why a buy
 * lands in the plan's "No price yet" section.
 *
 * `currency` is an ISO code. It is required whenever `unit_cost` is set, because a price
 * with no code is read as the base currency downstream, which would understate a foreign
 * price without anything being able to detect it.
 */
export interface ProductSupplierSourcingTerms {
  moq?: number | null;
  order_multiple?: number | null;
  unit_cost?: number | string | null;
  currency?: string | null;
  is_primary_supplier?: boolean;
}

export interface ProductSupplier extends ProductSupplierSourcingTerms {
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

export interface ProductSupplierFormData extends ProductSupplierSourcingTerms {
  product_id: string;
  supplier_id: string;
  /** Required by the backend: the column is NOT NULL with no default. */
  standard_lead_time_days: number;
  lead_time_days?: number;
}
