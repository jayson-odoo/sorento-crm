import { z } from 'zod';

/** Select value when no explicit default supplier is chosen (backend: null → oldest supplier). */
export const NO_DEFAULT_SUPPLIER_VALUE = '__none__';

/** Select value when no default approver is configured. */
export const NO_DEFAULT_APPROVER_VALUE = '__none__';

export const GeneralSettingsSchema = z.object({
  name: z.string().min(1, 'Company name is required'),
  logoFile: z
    .instanceof(File)
    .nullable()
    .optional()
    .refine(
      (file) => !file || file.size <= 1024 * 1024, // Check if file is not present or <= 1MB
      { message: 'Logo file must be smaller than 1MB' },
    ),
  logoAction: z.string().optional(),
  active: z.boolean(),
  address: z.string().nullable().optional(),
  websiteURL: z
    .string()
    .url('Must be a valid URL')
    .or(z.literal(''))
    .optional(),
  supportEmail: z.string().email('Must be a valid email'),
  supportPhone: z.string().nullable().optional(),
  language: z.string(),
  timezone: z.string(),
  currency: z.string(),
  currencyFormat: z.string(),
  defaultProductSupplierId: z.string(),
  defaultProductStandardLeadTimeDays: z.coerce.number().int().min(0).max(10950),
  takeoverCooldownSeconds: z.coerce.number().int().min(0).max(3600),
  formSlaGraceSeconds: z.coerce.number().int().min(0).max(600),
  /** SCM front planning: the grain new plans are decided at (AC-F01). */
  planGrain: z.enum(['product', 'location']),
  purchaseRequestDefaultApproverUserId: z.string(),
  sponsorshipFormDefaultApproverUserId: z.string(),
});

export type GeneralSettingsSchemaType = z.infer<typeof GeneralSettingsSchema>;
