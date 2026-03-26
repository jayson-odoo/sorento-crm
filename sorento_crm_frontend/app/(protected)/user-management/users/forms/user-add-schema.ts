import { z } from 'zod';

export const UserAddSchema = z.object({
  name: z
    .string()
    .nonempty({ message: 'Name is required.' })
    .min(2, { message: 'Name must be at least 2 characters long.' })
    .max(50, { message: 'Name must not exceed 50 characters.' }),
  email: z.string().email({
    message: 'Please enter a valid email address.',
  }),
  contact_number: z.string().optional().nullable(),
  roleIds: z.array(z.string()).min(1, {
    message: 'At least one role is required.',
  }),
  agent_ids: z.array(z.string()).optional(),
  superior_id: z.string().optional().nullable(),
});

export type UserAddSchemaType = z.infer<typeof UserAddSchema>;
