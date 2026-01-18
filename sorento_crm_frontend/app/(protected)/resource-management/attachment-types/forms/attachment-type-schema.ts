import { z } from 'zod';

export const AttachmentTypeSchema = z.object({
  type_name: z
    .string()
    .min(1, { message: 'Type name is required.' })
    .max(100, { message: 'Type name must not exceed 100 characters.' }),
  description: z
    .string()
    .max(1000, { message: 'Description must not exceed 1000 characters.' })
    .optional()
    .nullable(),
  allowed_extensions: z
    .string()
    .min(1, { message: 'Allowed extensions are required.' })
    .max(255, { message: 'Allowed extensions must not exceed 255 characters.' }),
  max_file_size_mb: z
    .number()
    .min(1, { message: 'Max file size must be at least 1 MB.' })
    .max(10000, { message: 'Max file size must not exceed 10000 MB.' }),
});

export type AttachmentTypeSchemaType = z.infer<typeof AttachmentTypeSchema>;
