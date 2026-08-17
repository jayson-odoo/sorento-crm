import { z } from 'zod';

export const ContactEditSchema = z.object({
  phone_number: z
    .string()
    .min(1, 'Phone number is required')
    .regex(/^\+?[1-9]\d{1,14}$/, 'Phone number must be in E.164 format (e.g., +1234567890)'),
  name: z.string().optional().nullable(),
  workspace_id: z.string().optional().nullable(),
  access_type_codes: z.array(z.string()),
  company_ids: z.array(z.string()).default([]),
  // AC-F4: per-contact sponsorship rollout switch.
  requires_registered_project: z.boolean().default(false),
});

export type ContactEditSchemaType = z.infer<typeof ContactEditSchema>;
