import { z } from 'zod';

export const AccessAgentSchema = z.object({
  code: z
    .string()
    .min(1, { message: 'Access agent code is required.' })
    .max(100, { message: 'Access agent code must not exceed 100 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Access agent code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  name: z
    .string()
    .min(3, { message: 'Access agent name must be at least 3 characters long.' })
    .max(255, { message: 'Access agent name must not exceed 255 characters.' }),
  description: z.string().max(2000, { message: 'Description must not exceed 2000 characters.' }).optional().nullable(),
  pic_respond_user_id: z.string().optional().nullable(),
  is_active: z.boolean(),
  assign_to_new_internal_contacts: z.boolean(),
});

export type AccessAgentSchemaType = z.infer<typeof AccessAgentSchema>;

export const ContactAgentAccessSchema = z.object({
  respond_contact_phone: z.string().min(1, { message: 'Respond contact phone is required.' }),
  respond_contact_name: z.string().optional().nullable(),
  agent_id: z.string().optional(),
  agent_ids: z.array(z.string()).optional(),
  is_allowed: z.boolean(),
  valid_from: z.date().optional().nullable(),
  valid_to: z.date().optional().nullable(),
})
  .refine((data) => (data.agent_ids?.length ?? 0) >= 1 || !!data.agent_id, {
    message: 'Select at least one access agent.',
    path: ['agent_ids'],
  })
  .refine((data) => {
    if (data.valid_from && data.valid_to) {
      return data.valid_to >= data.valid_from;
    }
    return true;
  }, {
    message: 'Valid to date must be after valid from date.',
    path: ['valid_to'],
  });

export type ContactAgentAccessSchemaType = z.infer<typeof ContactAgentAccessSchema>;
