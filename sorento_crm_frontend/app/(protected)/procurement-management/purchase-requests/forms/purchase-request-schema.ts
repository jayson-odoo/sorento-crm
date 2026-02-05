import { z } from 'zod';

const lineSchema = z.object({
  item_code: z.string().max(500).optional().nullable(),
  quantity: z.number().optional().nullable(),
  remark: z.string().max(2000).optional().nullable(),
});

export const PurchaseRequestSchema = z.object({
  request_type: z.enum(['purchase_request', 'sponsorship_form']),
  request_date: z.string().optional().nullable(),
  customer_name: z.string().max(500).optional().nullable(),
  project_title: z.string().max(500).optional().nullable(),
  purpose: z.string().max(500).optional().nullable(),
  expected_delivery_date: z.string().optional().nullable(),
  expected_po_date: z.string().optional().nullable(),
  expected_po_date_text: z.string().max(500).optional().nullable(),
  requested_by: z.string().max(255).optional().nullable(),
  requested_at: z.string().optional().nullable(),
  products: z.array(lineSchema),
});

export type PurchaseRequestSchemaType = z.infer<typeof PurchaseRequestSchema>;
