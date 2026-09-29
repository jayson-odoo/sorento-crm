import { z } from 'zod';

/**
 * `requireCurrent` is only true once the user already has a password
 * (`Account > Security`, plan 5.3) - a phone-only user sets one for the
 * first time with no current password to prove.
 */
export const getAccountPasswordSchema = (requireCurrent: boolean) =>
  z
    .object({
      currentPassword: requireCurrent
        ? z.string().min(1, { message: 'Current password is required.' })
        : z.string().optional(),
      newPassword: z
        .string()
        .min(8, { message: 'Password must be at least 8 characters long.' }),
      confirmNewPassword: z
        .string()
        .min(1, { message: 'Confirm your new password.' }),
    })
    .refine((values) => values.newPassword === values.confirmNewPassword, {
      message: 'Passwords do not match.',
      path: ['confirmNewPassword'],
    });

export type AccountPasswordSchemaType = z.infer<
  ReturnType<typeof getAccountPasswordSchema>
>;
