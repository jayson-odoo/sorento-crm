import { z } from 'zod';

export const FormSchema = z.object({
  code: z
    .string()
    .min(1, { message: 'Form code is required.' })
    .max(50, { message: 'Form code must not exceed 50 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Form code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  name: z
    .string()
    .min(1, { message: 'Form name is required.' })
    .max(255, { message: 'Form name must not exceed 255 characters.' }),
  purpose: z.string().max(2000, { message: 'Purpose must not exceed 2000 characters.' }).optional().nullable(),
  language: z.string().min(2, { message: 'Language is required.' }).max(10, { message: 'Language code must not exceed 10 characters.' }),
  is_active: z.boolean(),
  attachment_id: z.string().uuid().optional().nullable(),
});

export type FormSchemaType = z.infer<typeof FormSchema>;
