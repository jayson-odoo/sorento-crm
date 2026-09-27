import { z } from 'zod';

const userAddObject = z
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
  });

type UserAddValues = z.infer<typeof userAddObject>;

function refineEmailOrPhone(values: UserAddValues, ctx: z.RefinementCtx) {
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
}

/**
 * `companiesRequired` is true for a superadmin (the only viewer who sees and
 * sends Companies): then a user created from a WhatsApp contact needs at least
 * one company, or it is saved with no grants and nothing tells the owner
 * (plan 7; fix round 2, S4).
 */
export function buildUserAddSchema({ companiesRequired }: { companiesRequired: boolean }) {
  return userAddObject.superRefine((values, ctx) => {
    refineEmailOrPhone(values, ctx);
    if (companiesRequired && values.respond_contact_id && !values.companyIds?.length) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['companyIds'],
        message: 'Pick at least one company.',
      });
    }
  });
}

export const UserAddSchema = buildUserAddSchema({ companiesRequired: false });

export type UserAddSchemaType = z.infer<typeof UserAddSchema>;
