import { z } from 'zod';

export const UserProfileSchema = z.object({
  name: z.string().nonempty({
    message: 'Name is required.',
  }),
  roleId: z.string().nonempty({
    message: 'Role ID is required.',
  }),
  status: z.string().nonempty({
    message: 'Status is required.',
  }),
  respond_user_id: z.string().optional().nullable(),
  agent_ids: z.array(z.string()).optional(),
  superior_id: z.string().optional().nullable(),
});

export type UserProfileSchemaType = z.infer<typeof UserProfileSchema>;
