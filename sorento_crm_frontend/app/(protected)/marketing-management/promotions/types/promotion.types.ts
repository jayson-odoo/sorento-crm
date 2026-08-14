import type { Product } from '@/app/(protected)/master-data-management/products/types/product.types';

export interface PromotionListAttachment {
  id: string;
  attachment_id: string;
  is_primary?: boolean | null;
  sort_order?: number | null;
  attachment?: {
    id: string;
    original_filename: string;
    stored_filename?: string;
    mime_type?: string | null;
    file_size_bytes?: number | null;
  } | null;
}

export interface Promotion {
  id: string;
  description?: string | null;
  /** The kind of promotion, which decides what happens after end_date. */
  promotion_type_id?: string | null;
  promotion_type_code?: string | null;
  promotion_type_name?: string | null;
  /** "auto" (classified from the file name) or "manual" (a human corrected it). */
  promotion_type_source?: string | null;
  /** Ended, but its type says a salesman can still honour it. */
  expired_but_usable?: boolean;
  is_expired?: boolean;
  start_date: Date | null;
  end_date: Date | null;
  is_active: boolean;
  access_levels?: string[] | null;
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  products_count?: number;
  attachments?: PromotionListAttachment[] | null;
}

export interface PromotionFormData {
  description?: string;
  promotion_type_id?: string | null;
  /** Malaysia civil YYYY-MM-DD (matches API / backend promotion_dates). */
  start_date: string;
  end_date: string;
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
  promotion?: {
    id: string;
    is_active?: boolean | null;
    description?: string | null;
  };
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
