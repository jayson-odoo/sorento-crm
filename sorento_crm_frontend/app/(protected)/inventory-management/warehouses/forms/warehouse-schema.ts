import { z } from 'zod';

export const WarehouseSchema = z.object({
  warehouse_code: z
    .string()
    .min(1, { message: 'Warehouse code is required.' })
    .max(50, { message: 'Warehouse code must not exceed 50 characters.' }),
  warehouse_name: z
    .string()
    .min(1, { message: 'Warehouse name is required.' })
    .max(150, { message: 'Warehouse name must not exceed 150 characters.' }),
  location: z.string().max(255, { message: 'Location must not exceed 255 characters.' }).optional().nullable(),
  manager_id: z.string().uuid().optional().nullable(),
  is_active: z.boolean(),
});

export type WarehouseSchemaType = z.infer<typeof WarehouseSchema>;
