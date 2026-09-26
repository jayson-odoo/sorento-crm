import { z } from 'zod';

export const UserAddSchema = z
  .object({
    name: z
      .string()
      .nonempty({ message: 'Name is required.' })
      .min(2, { message: 'Name must be at least 2 characters long.' })
      .max(50, { message: 'Name must not exceed 50 characters.' }),
    // Optional when there is a phone, required when there is not (Q5, AC-41) -
    // enforced below, not by `.email()` alone.
    email: z.string().optional().nullable(),
    contact_number: z.string().optional().nullable(),
    respond_contact_id: z.string().optional().nullable(),
    roleIds: z.array(z.string()).min(1, {
      message: 'At least one role is required.',
    }),
    agent_ids: z.array(z.string()).optional(),
    superior_id: z.string().optional().nullable(),
    companyIds: z.array(z.string()).default([]),
  })
  .superRefine((values, ctx) => {
    const email = values.email?.trim();
    const phone = values.contact_number?.trim();
    if (email) {
      if (!z.string().email().safeParse(email).success) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['email'],
          message: 'Please enter a valid email address.',
        });
      }
      return;
    }
    if (!phone) {
      // Echoes the backend's `EMAIL_OR_PHONE_REQUIRED` message (S3 contract 1.2).
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['email'],
        message: 'Enter an email or a phone number.',
      });
    }
  });

export type UserAddSchemaType = z.infer<typeof UserAddSchema>;
