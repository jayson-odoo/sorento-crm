/** The town snapshot as the API serves it (schema 1). Which fields are present depends on the
 * viewer: no amounts without sales.reports.view, no names or ranks either, and no names on the
 * wallboard. */
export interface TownShop {
  /** A click key: the customer id for a full viewer, "s1".."sN" otherwise. Never rendered. */
  key: string;
  kind: 'shop' | 'stall';
  account_label: string | null;
  today_docs: number;
  name?: string;
  code?: string;
  rank?: number | null;
  today_amount?: string;
  ninety_day_amount?: string | null;
}

export interface TownSnapshot {
  schema: number;
  company_id: string;
  day: string;
  as_of: string;
  data_as_of: string | null;
  phase: 'day' | 'night';
  today: {
    amount?: string;
    invoice_count: number;
    credit_note_count: number;
    customer_count: number;
    dealer_customer_count: number;
  };
  compare?: { label: string; last_week_amount?: string; last_week_invoice_count: number };
  shops: TownShop[];
  warehouses: { pool: string; on_hand: number; available: number; locations: number }[];
  reorder: { below_count: number; set_count: number };
  deliveries?: { to_deliver: number };
  approvals: { total: number; purchase_requests: number; quotation_documents: number };
}

/** Nothing stored yet (the first tick of the day has not run). */
export interface TownPending {
  pending: true;
}

export type TownPayload = TownSnapshot | TownPending;

export function isPending(payload: TownPayload): payload is TownPending {
  return 'pending' in payload && payload.pending === true;
}
