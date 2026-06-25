import { z } from 'zod';

export const SLAPolicySchema = z.object({
  code: z
    .string()
    .min(1, { message: 'SLA policy code is required.' })
    .max(100, { message: 'SLA policy code must not exceed 100 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'SLA policy code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  name: z
    .string()
    .min(3, { message: 'SLA policy name must be at least 3 characters long.' })
    .max(255, { message: 'SLA policy name must not exceed 255 characters.' }),
  description: z.string().max(2000, { message: 'Description must not exceed 2000 characters.' }).optional().nullable(),
  is_active: z.boolean(),
});

export type SLAPolicySchemaType = z.infer<typeof SLAPolicySchema>;

export const SLAPolicyTierSchema = z.object({
  tier_level: z
    .union([z.number().int().min(1), z.undefined()])
    .transform((x) => (x === undefined ? 1 : x)),
  tier_name: z
    .string()
    .min(1, { message: 'Tier name is required.' })
    .max(255, { message: 'Tier name must not exceed 255 characters.' }),
  // Decimals allowed so sub-hour SLAs are expressible (0.5 = 30 minutes).
  response_hours: z
    .union([z.number().positive({ message: 'Must be greater than 0.' }), z.undefined()])
    .transform((x) => (x === undefined ? 1 : x)),
  resolution_hours: z
    .union([z.number().positive({ message: 'Must be greater than 0.' }), z.undefined()])
    .transform((x) => (x === undefined ? 1 : x)),
});

export type SLAPolicyTierSchemaType = z.infer<typeof SLAPolicyTierSchema>;
export type SLAPolicyTierFormInputType = z.input<typeof SLAPolicyTierSchema>;