import type { ProductCategory } from '../../products/types/product.types';

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
  display_order: number;
}
