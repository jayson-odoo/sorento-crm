import { z } from 'zod';

export const PublicHolidaySchema = z.object({
  date: z.string().min(1, { message: 'Date is required.' }),
  name: z.string().min(1, { message: 'Name is required.' }),
  description: z.string().optional(),
});

export type PublicHolidaySchemaType = z.infer<typeof PublicHolidaySchema>;
