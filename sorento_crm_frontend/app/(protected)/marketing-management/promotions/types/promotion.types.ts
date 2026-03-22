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
  promotion_group_id?: string | null;
  product_id: string;
  promotion_price?: number | null;
  display_order: number;
  product?: Product;
  discount_amount?: number;
  discount_percent?: number;
  /** Fraction off list for dealer cost (e.g. 0.37) */
  dealer_discount_percent?: number | null;
  dealer_cost?: number | null;
  /** list_price − dealer_cost */
  list_to_dealer_margin_amount?: number | null;
}

/** One buy-N paid, get M free combination within a promotion group. */
export interface FocTier {
  purchase_quantity: number;
  foc_quantity: number;
}

export interface PromotionGroup {
  id: string;
  promotion_id: string;
  group_name: string;
  sort_order: number;
  /** Multiple tiers, e.g. buy 10 get 1 and buy 25 get 5. */
  foc_tiers?: FocTier[] | null;
  /** Legacy: mirrors first tier when present. */
  purchase_quantity_for_foc?: number | null;
  foc_quantity?: number | null;
  promotion_products?: PromotionProduct[];
}

export interface PromotionDetail extends Promotion {
  products?: PromotionProduct[];
  promotion_groups?: PromotionGroup[];
  metrics?: {
    units_sold: number;
    revenue: number;
    total_discount: number;
    unique_customers: number;
    repeat_purchase_rate: number;
  };
}
