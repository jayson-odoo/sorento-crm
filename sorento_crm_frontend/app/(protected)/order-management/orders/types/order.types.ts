export interface Order {
  id: string;
  order_number: string;
  /**
   * Provenance gate. `autocount` rows are a read-only mirror of AutoCount and
   * only the annotation carve-out (internal_note / follow_up) may be changed;
   * every other mutation is server-guarded (403 AUTOCOUNT_READ_ONLY). `manual`
   * rows are full CRUD. `sync_source` is the raw upstream value behind it.
   */
  source?: 'autocount' | 'manual';
  sync_source?: string | null;
  /** Sorento-only note, survives re-sync. Editable even on autocount rows. */
  internal_note?: string | null;
  /** Sorento-only follow-up flag, survives re-sync. Editable on autocount rows. */
  follow_up?: boolean | null;
  order_date?: Date | null;
  estimated_delivery_date?: Date | null;
  actual_delivery_date?: Date | null;
  customer_id?: string | null;
  order_status_id?: string | null;
  created_by?: string | null;
  updated_by?: string | null;
  billing_address_id?: string | null;
  shipping_address_id?: string | null;
  created_time?: Date | null;
  debtor_code?: string | null;
  debtor_name?: string | null;
  agent?: string | null;
  is_cancelled?: boolean | null;
  remarks_cs?: string | null;
  /**
   * True when this DO is delivered AND linked to ≥1 complaint, so Remarks CS is
   * frozen (its fulfilment is historical / already notified). Backend-owned in
   * Phase 2; until then the FE falls back to a mock derivation. Drives the
   * readonly state of the Remarks CS field in OrderForm.
   */
  remarks_cs_locked?: boolean | null;
  order_type?: string | null;
  pickup_time?: string | null;
  checker?: string | null;
  transporter?: string | null;
  driver_name?: string | null;
  lorry_plate?: string | null;
  customer_ref?: string | null;
  delivery_remarks_cs?: string | null;
  delivery_remarks?: string | null;
  salesman?: string | null;
  trips?: number | null;
  warehouse?: string | null;
  delivery_days?: number | null;
  kpi_warning?: boolean | null;
  subtotal_amount: number;
  discount_amount: number;
  tax_amount: number;
  total_amount: number;
  remarks?: string | null;
  created_at: Date;
  updated_at: Date;
  deleted_at?: Date | null;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  customer?: {
    id: string;
    customer_code: string;
    customer_name: string;
  };
  order_status?: {
    id: string;
    status_code: string;
    status_name: string;
  };
  lines?: OrderLine[];
}

export interface OrderLine {
  id: string;
  order_id: string;
  line_sequence?: number;
  product_id: string;
  warehouse_id: string;
  quantity?: number | string | null;
  unit_price?: number | string | null;
  discount?: number | string | null;
  total?: number | string | null;
  tax?: number | string | null;
  total_excluding_tax?: number | string | null;
  total_including_tax?: number | string | null;
  created_at: string;
  updated_at: string;
  product?: { id: string; product_code?: string; product_name?: string };
  warehouse?: { id: string; warehouse_code?: string; warehouse_name?: string };
}

export interface OrderFormData {
  order_number: string;
  order_date: Date;
  // null = explicitly clear the date on update (undefined = leave unchanged).
  estimated_delivery_date?: Date | null;
  actual_delivery_date?: Date | null;
  customer_id?: string | null;
  order_status_id: string;
  billing_address_id?: string;
  shipping_address_id?: string;
  created_time?: Date;
  debtor_code?: string;
  debtor_name?: string;
  agent?: string;
  is_cancelled?: boolean;
  remarks_cs?: string;
  order_type?: string;
  pickup_time?: string;
  checker?: string;
  transporter?: string;
  driver_name?: string;
  lorry_plate?: string;
  customer_ref?: string;
  delivery_remarks_cs?: string;
  delivery_remarks?: string;
  salesman?: string;
  trips?: number;
  warehouse?: string;
  delivery_days?: number;
  kpi_warning?: boolean;
  subtotal_amount: number;
  discount_amount?: number;
  tax_amount?: number;
  total_amount: number;
  remarks?: string;
}

/** Annotation carve-out payload for the mirror note editor (both fields optional). */
export interface OrderAnnotationPayload {
  internal_note?: string | null;
  follow_up?: boolean;
}

export interface OrderLineFormData {
  product_id: string;
  warehouse_id: string;
  quantity?: number | string;
  unit_price?: number | string;
  discount?: number | string;
  total?: number | string;
  tax?: number | string;
  total_excluding_tax?: number | string;
  total_including_tax?: number | string;
}

export interface OrderDetail extends Order {
  lines?: OrderLine[];
  customer?: {
    id: string;
    customer_code: string;
    customer_name: string;
    contact_name?: string | null;
    email?: string | null;
    phone_number?: string | null;
  };
  order_status?: {
    id: string;
    status_code: string;
    status_name: string;
    description?: string | null;
  };
}
