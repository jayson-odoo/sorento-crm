import { z } from 'zod';

export const ProductSchema = z.object({
  // Tab 1: Basic Information
  product_code: z
    .string()
    .min(1, { message: 'Product code is required.' })
    .max(100, { message: 'Product code must not exceed 100 characters.' })
    .regex(/^[A-Za-z0-9 _\-./()+#]+$/, {
      message:
        'Product code may contain letters, numbers, spaces, and the symbols - _ . / ( ) + #.',
    }),
  product_name: z
    .string()
    .min(3, { message: 'Product name must be at least 3 characters long.' })
    .max(255, { message: 'Product name must not exceed 255 characters.' }),
  description: z.string().max(2000, { message: 'Description must not exceed 2000 characters.' }).optional().nullable(),
  category_id: z.string().uuid({ message: 'Category is required.' }),
  brand_id: z.string().uuid().optional().nullable(),
  barcode: z
    .string()
    .max(100, { message: 'Barcode must not exceed 100 characters.' })
    .optional()
    .nullable(),
  item_type: z.enum(['product', 'bundle', 'service', 'other']).optional().nullable(),
  is_active: z.boolean(),
  is_searchable: z.boolean(),

  // Tab 2: Pricing (coerce strings from API/inputs to numbers)
  list_price: z.coerce.number()
    .min(0, { message: 'List price cannot be negative.' })
    .max(999999999999.99, { message: 'List price is too large.' }),
  cost_price: z
    .union([z.coerce.number(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v >= 0 && v <= 999999999999.99), {
      message: 'Cost price must be between 0 and 999999999999.99.',
    }),
  invoice_price: z
    .union([z.coerce.number(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v >= 0 && v <= 999999999999.99), {
      message: 'Invoice price must be between 0 and 999999999999.99.',
    }),

  // Tab 3: Specifications
  weight: z
    .union([z.coerce.number(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v > 0), {
      message: 'Weight must be a positive number.',
    }),
  dimensions_length: z
    .union([z.coerce.number(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v > 0), {
      message: 'Length must be a positive number.',
    }),
  dimensions_width: z
    .union([z.coerce.number(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v > 0), {
      message: 'Width must be a positive number.',
    }),
  dimensions_height: z
    .union([z.coerce.number(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v > 0), {
      message: 'Height must be a positive number.',
    }),
  warranty_months: z
    .union([z.coerce.number().int(), z.null()])
    .optional()
    .nullable()
    .refine((v) => v === null || v === undefined || (typeof v === 'number' && v >= 0), {
      message: 'Warranty months cannot be negative.',
    }),
  has_serial_tracking: z.boolean(),
  has_batch_tracking: z.boolean(),
  reorder_level: z.coerce.number().int().min(0, { message: 'Reorder level cannot be negative.' }),
  reorder_quantity: z.coerce.number().int().min(0, { message: 'Reorder quantity cannot be negative.' }),

  // Tab 4: Unit of Measure
  base_uom_id: z.string().uuid({ message: 'Base unit of measure is required.' }),
});

export type ProductSchemaType = z.infer<typeof ProductSchema>;
