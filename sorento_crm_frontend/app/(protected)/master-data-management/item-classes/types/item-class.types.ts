/**
 * An item class: a tenant-maintained grouping a product can carry and a contact's brand
 * access can be narrowed to.
 *
 * API contract: `/api/v1/master-data/item-classes` (list / select / get / post / put) and the
 * deferred record action `item_class.delete`.
 */
export interface ItemClass {
  id: string;
  item_class_code: string;
  item_class_name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
  product_count: number;
}

export interface ItemClassFormData {
  item_class_code: string;
  item_class_name: string;
  description?: string | null;
  is_active: boolean;
}

/** One class as a select option source - active rows only. */
export interface ItemClassSelectItem {
  id: string;
  item_class_code: string;
  item_class_name: string;
  is_active: boolean;
}
