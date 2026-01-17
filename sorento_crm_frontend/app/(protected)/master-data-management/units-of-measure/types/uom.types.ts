import type { UnitOfMeasure } from '@/app/(protected)/master-data-management/products/types/product.types';

export type { UnitOfMeasure };

export interface UOMFormData {
  uom_code: string;
  uom_name: string;
  description?: string;
  base_uom_id?: string;
  conversion_factor?: number;
}
