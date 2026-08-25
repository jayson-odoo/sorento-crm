/**
 * The planning class a sales order was classified into (`sales_orders.demand_class` -
 * `app.services.scm.demand_class` on the backend): `project`, `retail`, or unset. Shared
 * between the sales-order list's Type column and the detail page's Order type field so the
 * two screens read the same chip for the same order.
 *
 * Deliberately separate from `order_type_label` (the ERP document type, which the AutoCount
 * book states on almost none of its 15,000 rows): this is the answer a buyer actually asked
 * for when the captain said "the type appears empty on nearly every row" - the classification
 * agents already ran, not the rarely-stated document type.
 *
 * The VOCABULARY and the LABELS come from the sales-agents master's own module, which is
 * where an admin sets a class and therefore the page the captain pointed at as the reference.
 * Two copies disagreed - this one painted retail `success` (green) while that one painted
 * every class `info` - so the same word read as two different chips on two screens one click
 * apart. One list, one label map, one palette.
 */
import {
  DEMAND_CLASS_LABEL,
  demandClassLabel,
} from '@/app/(protected)/master-data-management/sales-agents/lib/demandClass';

export type DemandClassValue = 'project' | 'retail' | null | undefined;

export type DemandClassBadgeVariant = 'info' | 'secondary';

export interface DemandClassBadge {
  variant: DemandClassBadgeVariant;
  label: string;
}

/** Project vs Retail chip, off `demand_class`. An unset class reads a MUTED
 *  "Unclassified" rather than being hidden - it is a real, common answer (most of the
 *  book), not a loading state. */
export function demandClassBadge(value: string | null | undefined): DemandClassBadge {
  const label = demandClassLabel(value);
  if (label && value && value in DEMAND_CLASS_LABEL) return { variant: 'info', label };
  return { variant: 'secondary', label: 'Unclassified' };
}
