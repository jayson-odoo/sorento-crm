import { z } from 'zod';

export const UserProfileSchema = z.object({
  name: z.string().min(1, { message: 'Name is required.' }),
  roleIds: z.array(z.string()).min(1, { message: 'At least one role is required.' }),
  status: z.string().min(1, { message: 'Status is required.' }),
  respond_user_id: z.string().optional().nullable(),
  agent_ids: z.array(z.string()).optional(),
  superior_id: z.string().optional().nullable(),
});

export type UserProfileSchemaType = z.infer<typeof UserProfileSchema>;
