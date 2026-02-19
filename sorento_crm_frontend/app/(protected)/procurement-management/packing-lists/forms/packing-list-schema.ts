import { z } from 'zod';

export const shipmentLineSchema = z.object({
  product_id: z.string().min(1, 'Product is required'),
  quantity_shipped: z.coerce.number().int().min(1, 'Quantity must be at least 1'),
});

export const packingListSchema = z.object({
  shipment_number: z.string().min(1, 'Shipment number is required'),
  supplier_id: z.string().optional(),
  shipment_date: z.string().min(1, 'Shipment date is required'),
  expected_arrival_date: z.string().optional(),
  actual_arrival_date: z.string().optional(),
  bill_of_lading_number: z.string().optional(),
  shipping_container_number: z.string().optional(),
  invoice_number: z.string().optional(),
  shipment_status: z.string().default('in_transit'),
  shipment_lines: z.array(shipmentLineSchema).default([]),
});

export type PackingListSchemaType = z.infer<typeof packingListSchema>;
