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
  is_active: z.boolean().default(true),
});

export type SLAPolicySchemaType = z.infer<typeof SLAPolicySchema>;

export const SLAPolicyTierSchema = z.object({
  tier_level: z
    .number()
    .int({ message: 'Tier level must be a whole number.' })
    .min(1, { message: 'Tier level must be at least 1.' }),
  tier_name: z
    .string()
    .min(1, { message: 'Tier name is required.' })
    .max(255, { message: 'Tier name must not exceed 255 characters.' }),
  response_hours: z
    .number()
    .int({ message: 'Response hours must be a whole number.' })
    .min(1, { message: 'Response hours must be at least 1.' }),
});

export type SLAPolicyTierSchemaType = z.infer<typeof SLAPolicyTierSchema>;
