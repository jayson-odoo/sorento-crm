import type { Promotion } from '../../promotions/types/promotion.types';
import type { Product } from '../../../master-data-management/products/types/product.types';

export interface PromotionProductListItem {
  id: string;
  promotion_id: string;
  product_id: string;
  promotion_price?: number | null;
  /** The brand's promotions carry no selling price (Cabana): show none, not list price. */
  no_selling_price?: boolean;
  display_order: number;
  created_at: Date;
  updated_at: Date;
  promotion?: Promotion;
  product?: Product;
  discount_amount?: number;
  discount_percent?: number;
}
