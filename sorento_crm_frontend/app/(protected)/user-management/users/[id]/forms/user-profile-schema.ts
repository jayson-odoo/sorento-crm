import { z } from 'zod';

export const UserProfileSchema = z.object({
  name: z.string().min(1, { message: 'Name is required.' }),
  email: z.string().min(1, { message: 'Email is required.' }).email({ message: 'Enter a valid email address.' }),
  roleIds: z.array(z.string()).min(1, { message: 'At least one role is required.' }),
  status: z.string().min(1, { message: 'Status is required.' }),
  respond_user_id: z.string().optional().nullable(),
  contact_number: z.string().optional().nullable(),
  tier: z
    .union([z.number().int(), z.literal(''), z.null(), z.undefined()])
    .optional()
    .nullable()
    .transform((v): number | null | undefined =>
      v === '' || v === null || v === undefined ? null : typeof v === 'number' ? v : Number(v)
    ),
  agent_ids: z.array(z.string()).optional(),
  superior_id: z.string().optional().nullable(),
  respond_contact_id: z.string().optional().nullable(),
  notify_whatsapp: z.boolean().optional(),
  notify_whatsapp_summary: z.boolean().optional(),
  notify_email_on_assignment: z.boolean().optional(),
  notify_email_on_escalation: z.boolean().optional(),
  notify_whatsapp_on_assignment: z.boolean().optional(),
  notify_whatsapp_on_escalation: z.boolean().optional(),
  notify_email_on_deadline_extended: z.boolean().optional(),
  notify_whatsapp_on_deadline_extended: z.boolean().optional(),
  notify_email_on_product_discontinued: z.boolean().optional(),
  notify_whatsapp_on_product_discontinued: z.boolean().optional(),
});

export type UserProfileSchemaType = z.infer<typeof UserProfileSchema>;
