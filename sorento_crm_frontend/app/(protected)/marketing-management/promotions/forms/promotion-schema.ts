import { z } from 'zod';

export const PromotionSchema = z.object({
  promo_code: z
    .string()
    .min(1, { message: 'Promo code is required.' })
    .max(50, { message: 'Promo code must not exceed 50 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Promo code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  name: z
    .string()
    .min(3, { message: 'Promotion name must be at least 3 characters long.' })
    .max(255, { message: 'Promotion name must not exceed 255 characters.' }),
  promo_type: z.enum(['price_override', 'discount_percent', 'discount_amount', 'bundle', 'other'], {
    errorMap: () => ({ message: 'Please select a valid promotion type.' }),
  }),
  description: z.string().max(2000, { message: 'Description must not exceed 2000 characters.' }).optional().nullable(),
  start_date: z.date({ required_error: 'Start date is required.' }),
  end_date: z.date({ required_error: 'End date is required.' }),
  is_active: z.boolean(),
  access_levels: z.array(z.enum(['dealer', 'end_user'])).min(1, {
    message: 'Select at least one access level.',
  }),
}).refine((data) => data.end_date >= data.start_date, {
  message: 'End date must be after start date.',
  path: ['end_date'],
});

export type PromotionSchemaType = z.infer<typeof PromotionSchema>;
