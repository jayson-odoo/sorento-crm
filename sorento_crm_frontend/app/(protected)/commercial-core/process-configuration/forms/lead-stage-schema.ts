import { z } from 'zod';

export const LeadStageSchema = z.object({
  stage_code: z
    .string()
    .min(1)
    .max(50)
    .regex(/^[a-z0-9_-]+$/, { message: 'Use lowercase letters, numbers, dashes, and underscores only.' }),
  stage_name: z.string().min(1).max(100),
  sort_order: z.number().int().min(0),
  is_terminal: z.boolean(),
  allows_conversion: z.boolean(),
});

export type LeadStageSchemaType = z.infer<typeof LeadStageSchema>;
