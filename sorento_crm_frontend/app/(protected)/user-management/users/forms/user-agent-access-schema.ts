import { z } from 'zod';

export const UserAgentAccessSchema = z.object({
  agent_id: z.string().min(1, { message: 'Agent ID is required.' }),
  is_allowed: z.boolean(),
  valid_from: z.date().optional().nullable(),
  valid_to: z.date().optional().nullable(),
}).refine((data) => {
  if (data.valid_from && data.valid_to) {
    return data.valid_to >= data.valid_from;
  }
  return true;
}, {
  message: 'Valid to date must be after valid from date.',
  path: ['valid_to'],
});

export type UserAgentAccessSchemaType = z.infer<typeof UserAgentAccessSchema>;
