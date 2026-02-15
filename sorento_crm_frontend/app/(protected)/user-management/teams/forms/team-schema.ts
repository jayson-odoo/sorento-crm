import { z } from 'zod';

export const TeamSchema = z.object({
  name: z.string().min(1, { message: 'Team name is required.' }),
  description: z.string().optional().nullable(),
});

export type TeamSchemaType = z.infer<typeof TeamSchema>;
