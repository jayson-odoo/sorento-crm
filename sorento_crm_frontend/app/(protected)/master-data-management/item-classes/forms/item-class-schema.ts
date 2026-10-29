import { z } from 'zod';

export const ItemClassSchema = z.object({
  item_class_code: z
    .string()
    .trim()
    .min(1, { message: 'Code is required.' })
    .max(50, { message: 'Code must be 50 characters or fewer.' }),
  item_class_name: z
    .string()
    .trim()
    .min(1, { message: 'Name is required.' })
    .max(150, { message: 'Name must be 150 characters or fewer.' }),
  description: z.string().max(500, { message: 'Description must be 500 characters or fewer.' }),
  is_active: z.boolean(),
});

export type ItemClassSchemaType = z.infer<typeof ItemClassSchema>;
