import type { UnitOfMeasure } from '@/app/(protected)/master-data-management/products/types/product.types';

export type { UnitOfMeasure };

export interface UOMFormData {
  uom_code: string;
  uom_name: string;
  description?: string;
  base_uom_id?: string;
  conversion_factor?: number;
  /** `0..4`. Omitted on create resolves to 0; omitted on edit keeps the stored value. */
  decimal_places?: number;
  is_active: boolean;
}
