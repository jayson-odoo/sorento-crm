import { z } from 'zod';

export const ContactEditSchema = z.object({
  phone_number: z
    .string()
    .min(1, 'Phone number is required')
    .regex(/^\+?[1-9]\d{1,14}$/, 'Phone number must be in E.164 format (e.g., +1234567890)'),
  name: z.string().optional().nullable(),
  user_type: z.string().optional().nullable(),
});

export type ContactEditSchemaType = z.infer<typeof ContactEditSchema>;
