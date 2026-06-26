import { z } from 'zod';

/** Accepts number or string (e.g. from API or input) so "Expected number, received string" is avoided. */
const quantitySchema = z
  .union([z.number(), z.string()])
  .optional()
  .nullable();

/** Total Project Value: strict numeric, must fit Numeric(15,2) (abs < 10^13).
 *  Mirrors the backend validators.validate_project_value guard rail. */
const projectValueSchema = z
  .union([z.number(), z.string()])
  .optional()
  .nullable()
  .refine((v) => v == null || v === '' || !Number.isNaN(Number(v)), {
    message: 'Total project value must be a number.',
  })
  .refine((v) => v == null || v === '' || Number.isNaN(Number(v)) || Math.abs(Number(v)) < 1e13, {
    message: 'Total project value is too large (max 9,999,999,999,999.99).',
  });

const lineSchema = z.object({
  item_code: z.string().max(500).optional().nullable(),
  quantity: quantitySchema,
  remark: z.string().max(2000).optional().nullable(),
  unit_price: quantitySchema,
  total: quantitySchema,
});

export const PurchaseRequestSchema = z.object({
  request_type: z.enum(['purchase_request', 'sponsorship_form']),
  request_number: z.string().max(50).optional().nullable(),
  request_date: z.string().optional().nullable(),
  customer_name: z.string().max(500).optional().nullable(),
  project_title: z.string().max(500).optional().nullable(),
  purpose: z.string().max(500).optional().nullable(),
  delivery_address: z.string().max(2000).optional().nullable(),
  total_project_value: projectValueSchema,
  total_project_value_text: z.string().max(2000).optional().nullable(),
  sponsor_subject: z.string().max(500).optional().nullable(),
  sponsor_subject_other: z.string().max(2000).optional().nullable(),
  expected_delivery_date: z.string().optional().nullable(),
  expected_po_date: z.string().optional().nullable(),
  expected_po_date_text: z.string().max(500).optional().nullable(),
  requested_by: z.string().max(255).optional().nullable(),
  requested_at: z.string().optional().nullable(),
  contact_id: z.string().max(500).optional().nullable(),
  space_id: z.string().max(500).optional().nullable(),
  products: z.array(lineSchema),
});

export type PurchaseRequestSchemaType = z.infer<typeof PurchaseRequestSchema>;
