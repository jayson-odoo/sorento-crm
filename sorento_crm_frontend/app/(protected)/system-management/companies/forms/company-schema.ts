import { z } from 'zod';

export const CompanySchema = z.object({
  name: z
    .string()
    .min(1, { message: 'Company name is required.' })
    .max(150, { message: 'Company name must not exceed 150 characters.' }),
  code: z
    .string()
    .min(1, { message: 'Company code is required.' })
    .max(20, { message: 'Company code must not exceed 20 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Company code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  is_active: z.boolean(),
  // AutoCount company reference - links this CRM company to its AutoCount master.
  autocount_ref: z
    .string()
    .max(150, { message: 'AutoCount reference must not exceed 150 characters.' })
    .optional()
    .nullable()
    .or(z.literal('')),
  logo_url: z
    .string()
    .url({ message: 'Logo URL must be a valid URL.' })
    .optional()
    .nullable()
    .or(z.literal('')),
});

export type CompanySchemaType = z.infer<typeof CompanySchema>;
