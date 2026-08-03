import { z } from 'zod';

export const WarehouseSchema = z.object({
  warehouse_code: z
    .string()
    .min(1, { message: 'System location is required.' })
    .max(50, { message: 'System location must not exceed 50 characters.' }),
  warehouse_name: z
    .string()
    .max(150, { message: 'System location description must not exceed 150 characters.' })
    .optional()
    .nullable(),
  location: z.string().max(255, { message: 'Warehouse must not exceed 255 characters.' }).optional().nullable(),
  manager_id: z.string().uuid().optional().nullable(),
  is_active: z.boolean(),
  // Planning configuration. Both change what the reorder plan buys.
  counts_as_available: z.boolean(),
  pool_warehouse_id: z.string().uuid().optional().nullable(),
});

export type WarehouseSchemaType = z.infer<typeof WarehouseSchema>;
