/** The town snapshot as the API serves it (schema 1). Which fields are present depends on the
 * viewer: no amounts without sales.reports.view, no names or ranks either, and no names on the
 * wallboard. */
export interface TownShop {
  /** A click key: the customer id for a full viewer, otherwise an opaque "s" + 12 hex key that stays the
   * same for the shop all day (the sale beat diffs keys between polls). Never rendered. */
  key: string;
  kind: 'shop' | 'stall';
  account_label: string | null;
  today_docs: number;
  name?: string;
  code?: string;
  rank?: number | null;
  today_amount?: string;
  ninety_day_amount?: string | null;
  /** TOWN-PROJECT-CITY: the dealer's state (a `my_state` value), from its delivery orders' postcode; null = not known */
  state?: string | null;
}

/** One sales type's share of today (TOWN-PROJECT-CITY): `amount` only for a viewer who may see amounts. */
export interface TownSplitPart {
  amount?: string;
  invoice_count: number;
}

/** An open project drawn as a site. Its look follows its own dates; `stage` is our sales stage (a flag only).
 * `name`, `code` and `estimated_value` are absent on the redacted and wallboard variants, where `key` is opaque. */
export interface TownSite {
  key: string;
  name?: string;
  code?: string | null;
  stage: string | null;
  /** the stage as the CRM names and colours it (the status row); absent on a snapshot built before 12 Nov */
  stage_label?: string | null;
  stage_color?: string | null;
  final_negotiation: boolean;
  state: string | null;
  launch_date: string | null;
  delivery_date: string | null;
  estimated_value?: string | null;
}

export interface TownProjects {
  open_count: number;
  more: number;
  dormant: number;
  sites: TownSite[];
}

/** A customer that is a project's trading house; lit on a project invoice today. `name` only on the personal full view. */
export interface TownTradingHouse {
  key: string;
  name?: string;
  state: string | null;
  open_projects: number;
  today_docs: number;
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
    split?: { dealer: TownSplitPart; project: TownSplitPart; other: TownSplitPart };
  };
  compare?: { label: string; last_week_amount?: string; last_week_invoice_count: number };
  shops: TownShop[];
  warehouses: { pool: string; on_hand: number; available: number; locations: number }[];
  reorder: { below_count: number; set_count: number };
  /** `customers`: up to 6 destinations for the lorries, earliest due first (TOWN-V2 Q6). */
  deliveries?: {
    to_deliver: number;
    customers?: TownDueCustomer[];
    /** TOWN-PROJECT-CITY: project-type orders due, and up to 3 destination states (lorries to that state's project quarter) */
    project_orders?: number;
    project_states?: { state: string | null; orders: number }[];
  };
  approvals: { total: number; purchase_requests: number; quotation_documents: number };
  /** Open shipments from overseas suppliers (TOWN-V2). Absent on a snapshot built before it existed. */
  incoming?: TownIncoming;
  /** TOWN-PROJECT-CITY. Absent on a snapshot built before it existed. */
  projects?: TownProjects;
  trading_houses?: { more: number; rows: TownTradingHouse[] };
}

/** A customer with sales orders due today or overdue. `key` is its shop in `shops`; null when it has
 * no shop in the town (its lorry drives out of town), and then `name` names it on the personal view
 * only (absent on the redacted and wallboard variants). */
export interface TownDueCustomer {
  key: string | null;
  name?: string | null;
  orders: number;
}

/** One open shipment. `supplier` is absent on the redacted and wallboard variants. */
export interface TownShipment {
  shipment_number: string | null;
  container: string | null;
  supplier?: string | null;
  eta: string | null;
  products: number;
  quantity: number;
  late: boolean;
}

/** Two plain states (owner, 10 Nov): incoming = ETA today or later, or unknown; late = ETA passed.
 * Exact counts; `shipments` holds up to 30 incoming rows (soonest first) then up to 30 late rows. */
export interface TownIncoming {
  incoming: number;
  late: number;
  next_eta: string | null;
  shipments: TownShipment[];
}

/** Nothing stored yet (the first tick of the day has not run). */
export interface TownPending {
  pending: true;
}

export type TownPayload = TownSnapshot | TownPending;

export function isPending(payload: TownPayload): payload is TownPending {
  return 'pending' in payload && payload.pending === true;
}
