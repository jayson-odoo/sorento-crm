import { z } from 'zod';

export const spoAllocationSchema = z.object({
  spo_number: z.string().min(1, 'SPO number is required'),
  product_id: z.string().min(1, 'Product is required'),
  warehouse_id: z.string().min(1, 'Warehouse is required'),
  allocated_quantity: z.coerce.number().int().min(1, 'Allocated quantity must be at least 1'),
  inbound_shipment_id: z.string().min(1, 'Packing list / Inbound shipment is required'),
});

export type SPOAllocationSchemaType = z.infer<typeof spoAllocationSchema>;
