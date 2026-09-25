import type { ProductCategory } from '@/app/(protected)/master-data-management/products/types/product.types';

export type { ProductCategory };

export interface CategoryTreeItem extends ProductCategory {
  children?: CategoryTreeItem[];
  product_count?: number;
}

export interface CategoryFormData {
  category_code: string;
  category_name: string;
  description?: string;
  parent_category_id?: string;
  is_active: boolean;
  is_searchable: boolean;
  display_order: number;
  /** X (PLAN-chatbot-stock-ask-v2-24sep.md S1). Unset = no cap for this category. */
  chatbot_max_qty?: number | null;
  /** Y, days added to the ETA the assistant quotes. Unset = 0 days. */
  chatbot_eta_offset_days?: number | null;
}
