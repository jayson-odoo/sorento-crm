import { z } from 'zod';

export const BrandSchema = z.object({
  brand_code: z
    .string()
    .min(1, { message: 'Brand code is required.' })
    .max(50, { message: 'Brand code must not exceed 50 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Brand code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  brand_name: z
    .string()
    .min(1, { message: 'Brand name is required.' })
    .max(150, { message: 'Brand name must not exceed 150 characters.' }),
  manufacturer: z.string().max(150, { message: 'Manufacturer must not exceed 150 characters.' }).optional().nullable(),
  website: z.string().url({ message: 'Website must be a valid URL.' }).optional().nullable().or(z.literal('')),
  description: z.string().max(2000, { message: 'Description must not exceed 2000 characters.' }).optional().nullable(),
  logo_url: z.string().url({ message: 'Logo URL must be a valid URL.' }).optional().nullable().or(z.literal('')),
  is_active: z.boolean(),
});

export type BrandSchemaType = z.infer<typeof BrandSchema>;
