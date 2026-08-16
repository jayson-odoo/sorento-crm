import { z } from 'zod';

export const pickingLineSchema = z.object({
  product_id: z.string().min(1, 'Product is required'),
  quantity_expected: z.coerce.number().int().min(0, 'Quantity expected must be 0 or more'),
  quantity_picked: z.coerce.number().int().min(0, 'Quantity received must be 0 or more'),
  source_warehouse_id: z.string().min(1, 'Location is required'),
  spo_allocation_id: z.string().optional(),
  // Carried, never edited: it is what the imported sheet said this line was
  // received against, and an edit that dropped it would erase that evidence.
  spo_number_raw: z.string().nullish(),
  picked_condition: z.string().optional(),
});

export const grnSchema = z.object({
  picking_number: z.string().min(1, 'GRN number is required'),
  spo_number: z.string().optional(),
  picking_date: z.string().min(1, 'Picking date is required'),
  picking_status: z.enum(['draft', 'approved', 'rejected']).default('draft'),
  notes: z.string().optional(),
  picking_lines: z.array(pickingLineSchema).default([]),
});

export type PickingLineSchemaType = z.infer<typeof pickingLineSchema>;
export type GRNSchemaType = z.infer<typeof grnSchema>;
