import { z } from 'zod';

export const StockInquirySchema = z.object({
  salesperson: z.string().max(255).optional().nullable(),
  product_code: z.string().max(255).optional().nullable(),
  item_description: z.string().max(2000).optional().nullable(),
  project_customer: z.string().max(255).optional().nullable(),
  project_name: z.string().max(255).optional().nullable(),
  quantity: z.number().positive().optional().nullable(),
  delivery_date: z.date().optional().nullable(),
  brand: z.string().max(255).optional().nullable(),
  additional_remark: z.string().max(2000).optional().nullable(),
  purchasing_response: z.string().max(2000).optional().nullable(),
});

export type StockInquirySchemaType = z.infer<typeof StockInquirySchema>;
