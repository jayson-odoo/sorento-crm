import { z } from 'zod';

export const shipmentLineSchema = z.object({
  product_id: z.string().min(1, 'Product is required'),
  quantity_shipped: z.coerce.number().int().min(1, 'Quantity must be at least 1'),
  /**
   * Carried, never edited here. A mixed container's lines are the only record of which
   * factory loaded what - zod strips a key it does not declare, so leaving this out would
   * make every hand save of a mixed container an unattributed one.
   */
  supplier_id: z.string().optional(),
});

/**
 * Clearance fields, editable by hand as the contingency path.
 *
 * The workbook import is the normal way these arrive, but it is not the only
 * one: when the import has not run yet, or a liner publishes a revised ETA
 * between imports, someone has to be able to type the date in. Every field is
 * optional - a packing list with no clearance data at all is the normal state
 * before the container moves.
 *
 * `source_sheet` is deliberately absent: it records WHERE a row came from, so
 * letting someone type it would turn provenance into a free-text opinion.
 */
export const clearanceSchema = z.object({
  loading_date: z.string().optional(),
  etc_date: z.string().optional(),
  etd_date: z.string().optional(),
  eta_delay_date: z.string().optional(),
  inspection_date: z.string().optional(),
  approval_date: z.string().optional(),
  gatepass_date: z.string().optional(),
  warehouse_arrival_date: z.string().optional(),
  informed_collection_date: z.string().optional(),
  collection_date: z.string().optional(),

  liner_code: z.string().optional(),
  china_forwarder: z.string().optional(),
  malaysia_forwarder: z.string().optional(),
  consignee: z.string().optional(),
  delivery_warehouse: z.string().optional(),
  loc: z.string().optional(),
  stacked: z.string().optional(),
  coa_permit_no: z.string().optional(),
  // Empty string when cleared, so coerce would turn "" into 0 - a real "0 free
  // days" and "not recorded" must stay distinguishable.
  free_days_available: z.union([z.coerce.number().int().min(0), z.literal('')]).optional(),
});

export type ClearanceSchemaType = z.infer<typeof clearanceSchema>;

/** The non-date clearance attributes, in the order the edit form renders them. */
export const CLEARANCE_ATTRIBUTE_FIELDS = [
  { name: 'liner_code', label: 'Liner' },
  { name: 'china_forwarder', label: 'China forwarder' },
  { name: 'malaysia_forwarder', label: 'Malaysia forwarder' },
  { name: 'consignee', label: 'Consignee' },
  { name: 'delivery_warehouse', label: 'Delivery warehouse' },
  { name: 'loc', label: 'Location' },
  { name: 'stacked', label: 'Stacked' },
  { name: 'coa_permit_no', label: 'COA permit no.' },
  { name: 'free_days_available', label: 'Free days available' },
] as const;

export const packingListSchema = clearanceSchema.extend({
  shipment_number: z.string().optional(),
  supplier_id: z.string().optional(),
  shipment_date: z.string().min(1, 'Shipment date is required'),
  estimated_arrival_date: z.string().optional(),
  actual_arrival_date: z.string().optional(),
  bill_of_lading_number: z.string().optional(),
  shipping_container_number: z.string().optional(),
  invoice_number: z.string().optional(),
  shipment_status: z.string().default('in_transit'),
  shipment_lines: z.array(shipmentLineSchema).default([]),
});

export type PackingListSchemaType = z.infer<typeof packingListSchema>;
