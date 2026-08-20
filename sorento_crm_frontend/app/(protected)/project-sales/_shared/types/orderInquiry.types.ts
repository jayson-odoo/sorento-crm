/**
 * Order inquiry rows: what purchasing is told to do (P10, AC-I1 to AC-I7).
 *
 * Quantities are strings, as everywhere else in this module: a 5,950 unit pre-order
 * netted against four dated deliveries has to add up to the unit, and a float round trip
 * does not guarantee that.
 *
 * Nothing here is shown as a UUID. The row carries the sales order NUMBER, the item CODE
 * and the warehouse CODE; the ids are only ever used to address the row.
 */

/** AC-I2's whole vocabulary, exactly as the backend stores it. */
export type OrderInquiryVerb =
  | 'ORDER'
  | 'RESERVE_AND_ORDER'
  | 'ADVANCE'
  | 'DELAY'
  | 'CHANGE_SO'
  | 'CANCEL_BALANCE'
  | 'PRE_ORDERED_DO_NOT_ORDER'
  | 'ALREADY_INBOUND'
  /**
   * A confirmed borrow left the DONOR location oversold, so the hole it opened is
   * buying work at that location (PLAN-fulfilment-planning 13.11). Its own verb: the
   * quantity belongs to the donor's location, not to the borrowing line's.
   */
  | 'BORROW_SHORTFALL'
  /**
   * A planning-change batch released a line's whole claim: the reserve freed at its own
   * location, and this Buy is no longer for this line - it is now for the pool
   * (PLAN-so-book-diff-replanning.md section 6). Informational, like DELAY/ADVANCE.
   */
  | 'RELEASE';

export type OrderInquiryState = 'raised' | 'actioned' | 'cancelled';

export interface OrderInquiryRow {
  id: string;
  order_inquiry_id: string;
  so_line_id?: string | null;
  project_sales_order_id?: string | null;
  /** The AutoCount document number when it has been adopted, else our own reference. */
  sales_order_ref?: string | null;
  /**
   * The trace back to the decision that raised the row (AC-D06), added by Stage 1C: the
   * sales order LINE number, the Project SO's own reference, and which confirmed revision
   * decided the quantity. Human identifiers only - a buyer expanding a Project
   * contribution reads the same words CS confirmed it with, never an id.
   */
  line_no?: number | null;
  project_so_ref?: string | null;
  decision_revision?: number | null;
  so_date?: string | null;
  project_customer?: string | null;
  is_amendment?: boolean;

  item_code?: string | null;
  qty: string;
  delivery_date?: string | null;
  /** Empty until an allocation is confirmed (AC-H5). Never defaulted to a location. */
  stock_location?: string | null;
  verb: OrderInquiryVerb | string;
  /** The verb in the client's own spelling, or the SPO reference for an inbound row. */
  remark?: string | null;
  spo_ref?: string | null;
  /** Which pre-order or inbound shipment covers this quantity (AC-I3a). */
  covered_by?: string | null;
  /** The date a DELAY moved from, the sales order a CHANGE SO points at. */
  note?: string | null;

  state: OrderInquiryState | string;
  actioned_at?: string | null;
  actioned_by_name?: string | null;
  created_at?: string | null;
}

export interface OrderInquiryDetail {
  id: string;
  project_sales_order_id: string;
  amendment_id?: string | null;
  state: string;
  raised_at?: string | null;
  /** The purchasing task the rows are attached to (AC-I4). */
  task_id?: string | null;
  task_name?: string | null;
  rows: OrderInquiryRow[];
}

export interface OrderInquirySummary {
  total: number;
  raised: number;
  actioned: number;
  cancelled: number;
}

export interface OrderInquiryListParams {
  query?: string;
  verb?: string;
  state?: string;
  sales_order_id?: string;
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
}

export interface OrderInquiryListEnvelope {
  data: OrderInquiryRow[];
  total: number;
  page: number;
  limit: number;
}

/* -------------------------------------------------------------- the worklist
 *
 * Purchasing's own list, across every project AND every adopted AutoCount order. The
 * per-project list above answers "what did this project raise"; this one answers "what
 * do I have to buy", which is a different question with a different owner, and the rows
 * an adopted order raises belong to no project at all so they appear on no other screen.
 *
 * The columns are the ones on the spreadsheet purchasing already works from
 * (`JAN - DEC 2026 ORDER.xlsx`, one sheet per delivery month), in its order, so the
 * screen and the file can be read side by side.
 */

export interface OrderInquiryWorklistRow {
  id: string;
  /** The core sales order's order date. The date on the document, not the raise date. */
  so_date?: string | null;
  so_number?: string | null;
  item_code?: string | null;
  product_name?: string | null;
  qty: string;
  delivery_date?: string | null;
  /** `BUIMACO / TUJU RESIDENCE`, or the core order's customer when there is no project. */
  project_customer?: string | null;
  /** Blank until a purchase order the row can be traced to exists. Never a guess. */
  supplier?: string | null;
  supplier_id?: string | null;
  po_number?: string | null;
  /**
   * Where the PO gets placed for: the donor an order-back row left oversold, the
   * confirmed allocation's warehouse for a plan/confirmed row, otherwise the line's own
   * fulfilment location. Blank when neither is known.
   */
  location?: string | null;
  /** Who sold it (`sales_orders.sales_agent_id` -> `sales_agents`), off the same core
   * sales order the S/O no column reaches. Null when the row reaches no core order, or
   * that order carries no agent. */
  agent_code?: string | null;
  agent_label?: string | null;
  state: OrderInquiryState | string;
  /** When purchasing was told. The spreadsheet's per-day tabs are this date. */
  raised_at?: string | null;
  verb: OrderInquiryVerb | string;
  note?: string | null;

  /** Addressing only, never rendered: how the row reaches its sales order. */
  project_id?: string | null;
  project_sales_order_id?: string | null;
  core_sales_order_id?: string | null;
  /** Came from the AutoCount book rather than a document authored here. */
  is_adopted?: boolean;
}

export interface OrderInquiryWorklistParams {
  query?: string;
  /** `YYYY-MM`, the delivery month, which is the sheet tab. */
  delivery_month?: string;
  /** `YYYY-MM-DD`, the day the rows were raised, which is the per-day tab. */
  raised_date?: string;
  state?: string;
  project_id?: string;
  supplier_id?: string;
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
}

export interface OrderInquiryWorklistEnvelope {
  data: OrderInquiryWorklistRow[];
  total: number;
  page: number;
  limit: number;
}

export interface OrderInquiryMonthTotal {
  /** `2026-01`. */
  month: string;
  /** `JAN 26`, spelled the way the sheet tab is. */
  label: string;
  rows: number;
  qty: string;
}

export interface OrderInquiryFacet {
  id: string;
  label: string;
  rows: number;
}

export interface OrderInquiryWorklistSummary {
  /** The visible set: every filter applied, the month included. */
  total_rows: number;
  total_qty: string;
  by_state: {
    raised: number;
    actioned: number;
    cancelled: number;
    total: number;
  };
  /**
   * The three axes the screen's own controls are built from. Each is computed with every
   * filter EXCEPT its own, because a control that empties itself the moment you use it
   * cannot be used a second time.
   */
  by_month: OrderInquiryMonthTotal[];
  suppliers: OrderInquiryFacet[];
  projects: OrderInquiryFacet[];
}

/* --------------------------------------------------------- the schedule matrix
 *
 * A 2D read of the SAME worklist rows the list shows (D1, reworked): the captain wanted
 * "vertically I can see by product, by sales order, by customer, by agent, then
 * horizontally is the dates ... by date, by month, by year" - a matrix like the
 * fulfilment planning board's, not a day-grid calendar. Built entirely CLIENT-SIDE off
 * one unpaged fetch of the already-filtered worklist: there is nothing here the server
 * needs to compute that grouping the rows in the browser cannot answer just as well, and
 * a second endpoint would be a second idea of what a row is.
 */

/** The vertical axis the captain named, in the order they named it. */
export type OrderInquiryMatrixAxis = 'product' | 'sales_order' | 'customer' | 'agent';

/** How the date axis is cut. Week is the default, matching the planning board's own. */
export type OrderInquiryMatrixGranularity = 'day' | 'week' | 'month' | 'year';

export type OrderInquiryMatrixBucketKind = 'dated' | 'no_date';

/** One column. Only buckets a row actually owes exist - never a full calendar grid. */
export interface OrderInquiryMatrixBucket {
  key: string;
  kind: OrderInquiryMatrixBucketKind;
  label: string;
  /** ISO date of the bucket's start, dated buckets only. The ordering key. */
  start?: string | null;
}

/** One row, whichever axis produced it. `key` is never rendered; `label` is. */
export interface OrderInquiryMatrixRow {
  key: string;
  label: string;
  /** Secondary text - a product's name under its code, an agent's name under their code. */
  description?: string | null;
}

/** One cell: this row, by this bucket, across every worklist row that lands there. */
export interface OrderInquiryMatrixCell {
  row_key: string;
  bucket_key: string;
  /** Summed across every contributing row. Decimal STRING, same reason the rows are. */
  qty: string;
  /** The contributing rows themselves - what a click on the cell drills down to. */
  rows: OrderInquiryWorklistRow[];
}
