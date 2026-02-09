import { z } from 'zod';

export const ProductSchema = z.object({
  // Tab 1: Basic Information
  product_code: z
    .string()
    .min(1, { message: 'Product code is required.' })
    .max(100, { message: 'Product code must not exceed 100 characters.' })
    .regex(/^[A-Za-z0-9_-]+$/, {
      message: 'Product code can only contain alphanumeric characters, dashes, and underscores.',
    }),
  product_name: z
    .string()
    .min(3, { message: 'Product name must be at least 3 characters long.' })
    .max(255, { message: 'Product name must not exceed 255 characters.' }),
  description: z.string().max(2000, { message: 'Description must not exceed 2000 characters.' }).optional().nullable(),
  category_id: z.string().uuid({ message: 'Category is required.' }),
  brand_id: z.string().uuid().optional().nullable(),
  item_type: z.enum(['product', 'bundle', 'service', 'other']).optional().nullable(),
  is_active: z.boolean(),

  // Tab 2: Pricing
  list_price: z
    .number()
    .positive({ message: 'List price must be greater than 0.' })
    .max(999999999999.99, { message: 'List price is too large.' }),
  cost_price: z
    .number()
    .positive({ message: 'Cost price must be greater than 0.' })
    .max(999999999999.99, { message: 'Cost price is too large.' })
    .optional()
    .nullable(),
  invoice_price: z
    .number()
    .positive({ message: 'Invoice price must be greater than 0.' })
    .max(999999999999.99, { message: 'Invoice price is too large.' })
    .optional()
    .nullable(),

  // Tab 3: Specifications
  weight: z
    .number()
    .positive({ message: 'Weight must be a positive number.' })
    .optional()
    .nullable(),
  dimensions_length: z
    .number()
    .positive({ message: 'Length must be a positive number.' })
    .optional()
    .nullable(),
  dimensions_width: z
    .number()
    .positive({ message: 'Width must be a positive number.' })
    .optional()
    .nullable(),
  dimensions_height: z
    .number()
    .positive({ message: 'Height must be a positive number.' })
    .optional()
    .nullable(),
  warranty_months: z
    .number()
    .int({ message: 'Warranty months must be an integer.' })
    .min(0, { message: 'Warranty months cannot be negative.' })
    .optional()
    .nullable(),
  has_serial_tracking: z.boolean(),
  has_batch_tracking: z.boolean(),
  reorder_level: z
    .number()
    .int({ message: 'Reorder level must be an integer.' })
    .min(0, { message: 'Reorder level cannot be negative.' }),
  reorder_quantity: z
    .number()
    .int({ message: 'Reorder quantity must be an integer.' })
    .min(0, { message: 'Reorder quantity cannot be negative.' }),

  // Tab 4: Unit of Measure
  base_uom_id: z.string().uuid({ message: 'Base unit of measure is required.' }),
});

export type ProductSchemaType = z.infer<typeof ProductSchema>;
