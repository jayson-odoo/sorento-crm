import type { Product } from '@/app/(protected)/master-data-management/products/types/product.types';

export type PromotionType = 'price_override' | 'discount_percent' | 'discount_amount' | 'bundle' | 'other';

export interface Promotion {
  id: string;
  promo_code: string;
  name: string;
  promo_type: PromotionType;
  description?: string | null;
  start_date: Date;
  end_date: Date;
  is_active: boolean;
  access_levels?: string[] | null;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  products_count?: number;
}

export interface PromotionFormData {
  promo_code: string;
  name: string;
  promo_type: PromotionType;
  description?: string;
  start_date: Date;
  end_date: Date;
  is_active: boolean;
  access_levels?: string[] | null;
  // Type-specific fields
  new_price?: number;
  discount_percentage?: number;
  discount_amount?: number;
}

export interface PromotionProduct {
  id: string;
  promotion_id: string;
  product_id: string;
  promotion_price?: number | null;
  display_order: number;
  product?: Product;
  discount_amount?: number;
  discount_percent?: number;
}

export interface PromotionDetail extends Promotion {
  products?: PromotionProduct[];
  metrics?: {
    units_sold: number;
    revenue: number;
    total_discount: number;
    unique_customers: number;
    repeat_purchase_rate: number;
  };
}
