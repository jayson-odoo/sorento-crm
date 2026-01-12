import { z } from 'zod';

export const SupplierSchema = z.object({
  supplier_code: z
    .string()
    .min(1, { message: 'Supplier code is required.' })
    .max(100, { message: 'Supplier code must not exceed 100 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Supplier code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  supplier_name: z
    .string()
    .min(3, { message: 'Supplier name must be at least 3 characters long.' })
    .max(255, { message: 'Supplier name must not exceed 255 characters.' }),
  contact_name: z.string().max(255, { message: 'Contact name must not exceed 255 characters.' }).optional().nullable(),
  email: z.string().email({ message: 'Invalid email address.' }).optional().nullable().or(z.literal('')),
  phone_number: z.string().max(50, { message: 'Phone number must not exceed 50 characters.' }).optional().nullable(),
  website: z.string().url({ message: 'Invalid website URL.' }).optional().nullable().or(z.literal('')),
  address_line1: z.string().max(255, { message: 'Address line 1 must not exceed 255 characters.' }).optional().nullable(),
  address_line2: z.string().max(255, { message: 'Address line 2 must not exceed 255 characters.' }).optional().nullable(),
  city: z.string().max(100, { message: 'City must not exceed 100 characters.' }).optional().nullable(),
  state: z.string().max(100, { message: 'State must not exceed 100 characters.' }).optional().nullable(),
  postal_code: z.string().max(20, { message: 'Postal code must not exceed 20 characters.' }).optional().nullable(),
  country: z.string().max(100, { message: 'Country must not exceed 100 characters.' }).optional().nullable(),
  payment_terms_days: z
    .number()
    .int({ message: 'Payment terms must be a whole number.' })
    .min(0, { message: 'Payment terms cannot be negative.' })
    .max(365, { message: 'Payment terms cannot exceed 365 days.' })
    .default(30),
  is_active: z.boolean().default(true),
});

export type SupplierSchemaType = z.infer<typeof SupplierSchema>;
