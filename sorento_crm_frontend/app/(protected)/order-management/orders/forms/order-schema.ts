import { z } from 'zod';

export const OrderSchema = z.object({
  order_number: z
    .string()
    .min(1, { message: 'Order number is required.' })
    .max(100, { message: 'Order number must not exceed 100 characters.' }),
  order_date: z.date({ required_error: 'Order date is required.' }),
  promised_delivery_date: z.date().optional().nullable(),
  actual_delivery_date: z.date().optional().nullable(),
  customer_id: z.string().min(1, { message: 'Customer is required.' }),
  order_status_id: z.string().min(1, { message: 'Order status is required.' }),
  billing_address_id: z.string().optional().nullable(),
  shipping_address_id: z.string().optional().nullable(),
  subtotal_amount: z
    .number()
    .min(0, { message: 'Subtotal amount cannot be negative.' })
    .default(0),
  discount_amount: z
    .number()
    .min(0, { message: 'Discount amount cannot be negative.' })
    .default(0)
    .optional()
    .nullable(),
  tax_amount: z
    .number()
    .min(0, { message: 'Tax amount cannot be negative.' })
    .default(0)
    .optional()
    .nullable(),
  total_amount: z
    .number()
    .min(0, { message: 'Total amount cannot be negative.' })
    .default(0),
  remarks: z.string().max(2000, { message: 'Remarks must not exceed 2000 characters.' }).optional().nullable(),
}).refine((data) => {
  // Calculate total if not provided
  if (data.total_amount === 0) {
    const calculatedTotal = data.subtotal_amount - (data.discount_amount || 0) + (data.tax_amount || 0);
    return calculatedTotal >= 0;
  }
  return true;
}, {
  message: 'Total amount calculation error.',
  path: ['total_amount'],
});

export type OrderSchemaType = z.infer<typeof OrderSchema>;
