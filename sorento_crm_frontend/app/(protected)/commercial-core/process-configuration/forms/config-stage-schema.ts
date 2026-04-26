import { z } from 'zod';

export const ConfigStageSchema = z.object({
  stage_code: z
    .string()
    .min(1)
    .max(50)
    .regex(/^[a-z0-9_-]+$/, { message: 'Use lowercase letters, numbers, dashes, and underscores only.' }),
  stage_name: z.string().min(1).max(100),
  description: z.string().max(2000).optional().nullable(),
  sort_order: z.number().int().min(0),
  is_terminal: z.boolean(),
  is_active: z.boolean(),
});

export type ConfigStageSchemaType = z.infer<typeof ConfigStageSchema>;
