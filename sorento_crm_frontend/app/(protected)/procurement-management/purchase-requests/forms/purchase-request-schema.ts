import { z } from 'zod';

/** Accepts number or string (e.g. from API or input) so "Expected number, received string" is avoided. */
const quantitySchema = z
  .union([z.number(), z.string()])
  .optional()
  .nullable();

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
  total_project_value: quantitySchema,
  sponsor_subject: z.string().max(500).optional().nullable(),
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
