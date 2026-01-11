import type { UnitOfMeasure } from '../../products/types/product.types';

export type { UnitOfMeasure };

export interface UOMFormData {
  uom_code: string;
  uom_name: string;
  base_uom_id?: string;
  conversion_factor?: number;
}
