import { z } from 'zod';

export const CountrySchema = z.object({
  code: z
    .string()
    .trim()
    .length(2, { message: 'Code must be exactly 2 letters.' })
    .regex(/^[A-Za-z]{2}$/, { message: 'Use 2 letters only.' }),
  name: z
    .string()
    .min(1, { message: 'Name is required.' })
    .max(100, { message: 'Name must be 100 characters or fewer.' }),
  is_active: z.boolean(),
});

export type CountrySchemaType = z.infer<typeof CountrySchema>;
