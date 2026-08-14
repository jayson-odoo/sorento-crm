import { z } from 'zod';

const isoDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, { message: 'Use the date picker to choose a date.' })
  .optional()
  .or(z.literal(''));

export const CertificateSchema = z
  .object({
    scheme: z
      .string()
      .min(1, { message: 'Scheme is required.' })
      .max(30, { message: 'Scheme must not exceed 30 characters.' }),
    certifying_body: z
      .string()
      .min(1, { message: 'Certifying body is required.' })
      .max(100, { message: 'Certifying body must not exceed 100 characters.' }),
    certificate_number: z
      .string()
      .min(1, { message: 'Certificate number is required.' })
      .max(100, { message: 'Certificate number must not exceed 100 characters.' }),
    issuer: z
      .string()
      .max(150, { message: 'Issuer must not exceed 150 characters.' })
      .optional()
      .or(z.literal('')),
    title: z
      .string()
      .max(200, { message: 'Title must not exceed 200 characters.' })
      .optional()
      .or(z.literal('')),
    status: z.enum(['active', 'archived']),
    issued_at: isoDate,
    valid_from: isoDate,
    valid_until: isoDate,
  })
  // Mirrors the RVW-1 rule the backend enforces: an expiry on or before the
  // start date is never a valid window.
  .refine(
    (data) => !data.valid_from || !data.valid_until || data.valid_until > data.valid_from,
    { message: 'Valid until must be after valid from.', path: ['valid_until'] },
  );

export type CertificateSchemaType = z.infer<typeof CertificateSchema>;
