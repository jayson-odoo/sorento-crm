/**
 * PM-SIMPLIFY: one PO's progress (`GET /purchase-orders/{po_id}/progress`) and moving an
 * area's date (`PUT /delivery-phases/{phase_id}/date`). Quantities arrive as decimal strings.
 */

export interface POProgressDelivery {
  phase_id: string | null;
  area_group: string | null;
  label: string | null;
  delivery_date: string | null;
  units: string;
  delivered: string;
  sales_order_id: string;
  provisional_ref: string;
  sales_order_status: string;
}

export interface POProgressLine {
  key: string;
  po_line_id: string | null;
  line_no: number;
  product_id: string | null;
  product_code: string | null;
  description: string | null;
  uom: string | null;
  ordered: string;
  scheduled: string;
  /** Scheduled minus ordered: below zero is short on the schedule, above is over. */
  schedule_gap: string;
  delivered: string;
  outstanding: string;
  next_delivery_date: string | null;
  deliveries: POProgressDelivery[];
}

export interface POProgressArea {
  phase_id: string;
  area_group: string;
  sequence: number;
  label: string | null;
  delivery_date: string | null;
  units: string;
  delivered: string;
  sales_orders: { id: string; provisional_ref: string; status: string }[];
}

export interface POProgress {
  purchase_order_id: string;
  schedule_version_id: string | null;
  lines: POProgressLine[];
  areas: POProgressArea[];
  totals: {
    ordered: string;
    scheduled: string;
    delivered: string;
    outstanding: string;
    next_delivery_date: string | null;
    schedule_short_lines: number;
    schedule_over_lines: number;
  };
}

export interface AreaDateRestoreLine {
  id: string;
  delivery_date: string | null;
}

export interface AreaDateChangeBody {
  delivery_date: string;
  restore_lines?: AreaDateRestoreLine[];
}

export interface AreaDateChangeResult {
  phase_id: string;
  area_group: string;
  label: string | null;
  delivery_date: string | null;
  previous_date: string | null;
  moved_lines: number;
  moved_orders: { id: string; provisional_ref: string }[];
  previous_lines: AreaDateRestoreLine[];
  amendments: {
    sales_order_id: string;
    provisional_ref: string;
    amendment_id: string | null;
    refused: string | null;
  }[];
}
