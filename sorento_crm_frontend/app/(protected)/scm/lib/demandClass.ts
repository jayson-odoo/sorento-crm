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
 */
export type DemandClassValue = 'project' | 'retail' | null | undefined;

export type DemandClassBadgeVariant = 'info' | 'success' | 'secondary';

export interface DemandClassBadge {
  variant: DemandClassBadgeVariant;
  label: string;
}

/** Project vs Retail chip, off `demand_class` - the same colours the Reorder plan's Order
 *  type chip uses (`PlanLinesGrid`), so the two screens do not invent two palettes for the
 *  same two words. An unset class reads a MUTED "Unclassified" rather than being hidden -
 *  it is a real, common answer (most of the book), not a loading state. */
export function demandClassBadge(value: string | null | undefined): DemandClassBadge {
  if (value === 'project') return { variant: 'info', label: 'Project' };
  if (value === 'retail') return { variant: 'success', label: 'Retail' };
  return { variant: 'secondary', label: 'Unclassified' };
}
