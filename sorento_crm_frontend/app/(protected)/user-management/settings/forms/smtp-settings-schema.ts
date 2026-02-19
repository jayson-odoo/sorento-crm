import { z } from 'zod';

export const SmtpSettingsSchema = z.object({
  smtp_host: z.string().min(1, 'SMTP host is required').optional().or(z.literal('')),
  smtp_port: z.string().optional(),
  smtp_secure: z.boolean(),
  smtp_username: z.string().optional(),
  smtp_password: z.string().optional(), // update-only; empty = keep existing
  smtp_from: z.string().optional(),
});

export type SmtpSettingsSchemaType = z.infer<typeof SmtpSettingsSchema>;
