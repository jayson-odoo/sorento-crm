import { z } from 'zod';

const ymd = z
  .string({ required_error: 'Date is required.' })
  .min(1, { message: 'Date is required.' })
  .regex(/^\d{4}-\d{2}-\d{2}$/, { message: 'Use a valid date.' });

export const PromotionSchema = z.object({
  description: z
    .string()
    .min(3, { message: 'Description must be at least 3 characters long.' })
    .max(2000, { message: 'Description must not exceed 2000 characters.' }),
  start_date: ymd,
  end_date: ymd,
  is_active: z.boolean(),
  access_levels: z.array(z.string()).min(1, {
    message: 'Select at least one access level.',
  }),
}).refine((data) => data.end_date >= data.start_date, {
  message: 'End date must be after start date.',
  path: ['end_date'],
});

export type PromotionSchemaType = z.infer<typeof PromotionSchema>;
