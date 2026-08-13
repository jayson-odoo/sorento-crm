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
  // Blank = unlimited. Enforced per entity row by the portal upload quota check.
  max_count_per_entity: z
    .number()
    .int({ message: 'Max attachments per record must be a whole number.' })
    .min(1, { message: 'Max attachments per record must be at least 1.' })
    .max(1000, { message: 'Max attachments per record must not exceed 1000.' })
    .nullable()
    .optional(),
  supports_field_linkage: z.boolean().optional(),
  triggers_n8n_webhook: z.boolean().optional(),
  // The cert-bearing signal. The external attachment endpoint honours the
  // certificate fields on an n8n payload ONLY when the attachment's type has
  // this on, so without it in the UI the register can never be switched on.
  is_certificate: z.boolean().optional(),
  // Ceiling used by the review rules: a validity span longer than this is
  // flagged as implausible rather than trusted. Blank = no ceiling.
  max_validity_months: z
    .number()
    .int({ message: 'Maximum validity must be a whole number of months.' })
    .min(1, { message: 'Maximum validity must be at least 1 month.' })
    .max(600, { message: 'Maximum validity must not exceed 600 months.' })
    .nullable()
    .optional(),
});

export type AttachmentTypeSchemaType = z.infer<typeof AttachmentTypeSchema>;
