import { z } from 'zod';

export const UserProfileSchema = z.object({
  name: z.string().min(1, { message: 'Name is required.' }),
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
});

export type UserProfileSchemaType = z.infer<typeof UserProfileSchema>;
