import type { Brand } from '@/app/(protected)/master-data-management/products/types/product.types';

export type { Brand };

export interface BrandFormData {
  brand_code: string;
  brand_name: string;
  manufacturer?: string;
  website?: string;
  description?: string;
  logo_url?: string;
  is_active: boolean;
  access_levels?: string[];
}
