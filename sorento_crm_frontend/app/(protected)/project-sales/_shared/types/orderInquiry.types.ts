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
   * The order back: a confirmed borrow left the DONOR location oversold, or CS wrote
   * `ORDER BACK` on the inquiry form against a document already on its way. Its own verb
   * because it is the only one that may be linked to an SPO allocation as well as to a
   * purchase order line (PLAN-scm-purchasing-uat-journey.md section 4b).
   */
  | 'ORDER_BACK'
  /**
   * A planning-change batch released a line's whole claim: the reserve freed at its own
   * location, and this Buy is no longer for this line - it is now for the pool
   * (PLAN-so-book-diff-replanning.md section 6). Informational, like DELAY/ADVANCE.
   */
  | 'RELEASE';

/**
 * `placed` reads "Linked" on every screen (AC-I1) and keeps its stored value: the row is
 * covered by links whose quantities sum to its own. `partly_linked` is the middle the
 * links table made expressible - some of the quantity is on a document, the rest is still
 * demand - and it is counted by `scm.committed_v` for exactly the unlinked remainder.
 */
export type OrderInquiryState =
  | 'raised'
  | 'partly_linked'
  | 'actioned'
  | 'cancelled'
  | 'placed';

/**
 * One placement: this row's quantity, or part of it, sitting on ONE purchase order line
 * or ONE SPO allocation (`projects.order_inquiry_links`, PLAN section 3.I). A row keeps
 * its FULL quantity and carries many links - never the split rows the cascade used to
 * write, which turned nine sales-order lines into eleven instructions.
 */
export interface OrderInquiryLink {
  id: string;
  /** Which book the document lives in. `spo` is only ever offered to an ORDER BACK row. */
  kind: 'po' | 'spo';
  /** `202607-S0105`, `SPO-2026/08-0061`. Never an id. */
  document: string;
  /** `L3` when the book numbered the line. Absent when it did not - never invented. */
  line_label?: string | null;
  qty: string;
  /** Where that document line lands the goods. Blank when the book names none. */
  location?: string | null;
  /** The document's own date, and the line's promised arrival. */
  issue_date?: string | null;
  expected_date?: string | null;
  /**
   * Q5's location fit, 1 to 5: 1 the row's own location, 2 the same group at another
   * site, 3 a site pool, 4 a sibling location at the site, 5 anywhere else. Never a
   * filter, only a rank - a link outside tier 1 is the split instruction for AutoCount.
   */
  tier?: number | null;
  /** Written by the cascade rather than by a person. */
  auto?: boolean;
  linked_at?: string | null;
  linked_by_name?: string | null;
  /** Addresses the PO popover. Null on an SPO link - there is no purchase order to open. */
  po_id?: string | null;
}

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
  /**
   * Every document this row is linked to, and how much of it sits there
   * (`projects.order_inquiry_links`). Empty on a raised row. `po_ref` above is the FIRST
   * link's document, kept as the one-word display the older screens read.
   */
  links?: OrderInquiryLink[];
  /** The sum of `links[].qty`. `qty - linked_qty` is what still flows to reorder planning. */
  linked_qty?: string;
  /** The document CS cited on an order back, which the cascade tries before any other. */
  cited_document?: string | null;
  po_ref?: string | null;
  po_line_id?: string | null;
  /**
   * Whether this row's own product still has an outstanding purchase-order line to link
   * (section G). The row action only offers "Link PO" when this is true - no dead end
   * where the dialog opens just to say there is nothing to link.
   */
  has_open_po_line?: boolean;

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
  /**
   * `OI-000123` - the number of the inquiry this row belongs to, off its own header.
   * What a person calls the instruction: "the inquiry on SO414033" stops being an answer
   * the moment an amendment raises the second one on that order.
   *
   * Optional only because a row written before the column existed carries none; every
   * inquiry raised since is stamped with one.
   */
  inquiry_no?: string | null;
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
  /**
   * What flows to reorder planning, for this row's own SO line (the captain, 20 Aug:
   * "show the quantity, quantity taken from PO, and the remaining quantity, cause this
   * is what flows to reorder planning"). `taken_from_po` sums every SIBLING placed
   * ORDER row on the same line; `remaining_open` sums every raised ORDER row on the
   * line - `committed_v`'s own confirmed leg, what still counts as demand. On a raised
   * row that includes itself.
   */
  taken_from_po?: string;
  remaining_open?: string;
  /**
   * Where this row's quantity actually sits (AC-I5): one entry per link, PO or SPO. The
   * "Linked to" column reads `linked_qty of qty` and then names each document. Empty on a
   * row nobody has linked - which is what "still to link" looks like.
   */
  links?: OrderInquiryLink[];
  linked_qty?: string;
  /** The document CS cited on an order back. Named on the row so the walk can honour it. */
  cited_document?: string | null;
  /** Same as `OrderInquiryRow.has_open_po_line`, for this cross-project worklist. */
  has_open_po_line?: boolean;
  /** Who sold it (`sales_orders.sales_agent_id` -> `sales_agents`), off the same core
   * sales order the S/O no column reaches. Null when the row reaches no core order, or
   * that order carries no agent. */
  agent_code?: string | null;
  agent_label?: string | null;
  state: OrderInquiryState | string;
  /** When purchasing was told. The spreadsheet's per-day tabs are this date. */
  raised_at?: string | null;
  /**
   * WHO told them, by name: the person who confirmed the supply revision that raised
   * THIS row, falling back to the inquiry header for an amendment-born row that has no
   * revision. Per row, never off the header alone - the header is re-stamped on every
   * reconfirm, so it would name the latest reconfirmer beside an older row's own clock.
   * Never an id: the cell prints this as it comes. Null when nobody was recorded.
   */
  raised_by_name?: string | null;
  verb: OrderInquiryVerb | string;
  note?: string | null;

  /** Addressing only, never rendered: how the row reaches its sales order. */
  project_id?: string | null;
  project_sales_order_id?: string | null;
  core_sales_order_id?: string | null;
  /** Came from the AutoCount book rather than a document authored here. */
  is_adopted?: boolean;
  /**
   * The placed purchase order this row traces to (same coalesce the `po_number` column
   * reads) - addresses the "PO no" cell's popup, `GET .../order-inquiries/po/{po_id}`.
   * Null on a row nobody has placed yet.
   */
  po_id?: string | null;
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
  /** The id of the person who raised the rows, picked off the summary's own list. */
  raised_by?: string;
  /**
   * Where the row is linked (AC-I5). `po` and `spo` mean "has at least one link of that
   * kind"; `none` means no link at all, which is the buyer's own worklist.
   */
  linked?: 'po' | 'spo' | 'none';
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
   * The axes the screen's own controls are built from. Each is computed with every
   * filter EXCEPT its own, because a control that empties itself the moment you use it
   * cannot be used a second time.
   */
  by_month: OrderInquiryMonthTotal[];
  suppliers: OrderInquiryFacet[];
  projects: OrderInquiryFacet[];
  /** The people who raised the rows in view, id + name. The "Raised by" filter's list. */
  raised_by: OrderInquiryFacet[];
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

/* --------------------------------------------------------- Place on PO (section G, G2)
 *
 * "identify which outstanding PO has quantity to fulfil this order inquiry, tag it, and
 * the quantity to be ordered is deducted" (the captain, 20 Aug). A raised ORDER row is
 * tagged to one or more open supplier PO lines; the row leaves `state = 'raised'` and the
 * reorder engine stops suggesting it. Untag ("Unplace") returns it.
 *
 * G2 (the captain, live-testing G, 20 Aug afternoon): placement now happens
 * AUTOMATICALLY - the cascade tags every raised row it can, earliest PO line first, ties
 * by document sequence, partial coverage allowed, POs only (never SPO-). This dialog
 * survives as OVERRIDE + AUDIT, not as the workflow: it opens already showing the
 * cascade's own preview (`default_take` per candidate), lets the taken quantity be
 * adjusted per line, and posts the whole allocation in one call. A row several lines
 * cover SPLITS on the backend - one row per PO line taken - so a placement can return
 * more than one row.
 */

/** One EXISTING tag already on a candidate's PO line - the row's expand. */
export interface OrderInquiryPoCandidateClaim {
  so_number?: string | null;
  item_code?: string | null;
  qty: string;
  placed_date?: string | null;
}

/**
 * One open document line the row could be linked to, in the walk's own order (Q5 + Q7):
 * the cited document first, then SPO allocations before PO lines on an ORDER BACK row,
 * then location tier, then the PO's issue date, then the line's expected date, then the
 * document number. Location NEVER filters a candidate out, it only ranks it.
 */
export interface OrderInquiryPoCandidate {
  /** Which book. `spo` candidates are offered to an ORDER BACK row and to nothing else. */
  kind: 'po' | 'spo';
  /** The PO line's id, or the SPO allocation's. Exactly one of the two is set. */
  po_line_id?: string | null;
  spo_allocation_id?: string | null;
  po_number: string;
  /** `L3` when the book numbered the line. */
  line_label?: string | null;
  /** Where that line lands the goods, and how well it fits the row's own location. */
  location?: string | null;
  tier: number;
  /** The document's own date - the cascade's FIRST key (Q7). */
  issue_date?: string | null;
  /** CS named this document on the order back, so the walk tries it before any other. */
  cited: boolean;
  /** Blank when the purchase order carries no supplier - never a guess. */
  supplier_name?: string | null;
  expected_date?: string | null;
  qty_ordered: string;
  qty_received: string;
  /** What OTHER placed rows already claim off this same line. */
  already_tagged: string;
  /** The line's balance, net of `already_tagged` - what is ACTUALLY left for this row. */
  remaining: string;
  /** `remaining >= ` the row's own quantity. */
  covers: boolean;
  /** The earliest candidate that covers the row. At most one candidate carries this. */
  recommended: boolean;
  /** The line's own held price. Blank when the purchase order carries none. */
  unit_cost?: string | null;
  currency?: string | null;
  /** The row's expand: every OTHER row already tagged onto this same PO line. */
  claims: OrderInquiryPoCandidateClaim[];
  /**
   * What the cascade would take off THIS line for THIS row (G2) - server-computed by the
   * SAME walk `auto_place_for_products` runs, so the dialog's preview and the auto pass
   * can never disagree. `"0"` when the cascade never reaches this line.
   */
  default_take: string;
}

/**
 * One line of a link - this row takes `qty` off ONE document line. Exactly one of
 * `po_line_id` / `spo_allocation_id` is set, the same rule the link row's own CHECK
 * constraint holds.
 */
export interface OrderInquiryPoAllocation {
  po_line_id?: string;
  spo_allocation_id?: string;
  qty: string;
}

/** `POST .../order-inquiries/auto-place` (G2 rule 4) - the worklist's "Auto-place". */
export interface AutoPlaceRequest {
  /** Omitted: every product carrying a raised ORDER/RESERVE & ORDER row. */
  product_ids?: string[];
}

export interface AutoPlaceResult {
  placed_rows: number;
  allocations: number;
  products_touched: number;
}

/**
 * `POST .../order-inquiries/unplace-all` (the captain, 20-21 Aug): "unplace all" for
 * the CURRENT worklist scope. The SAME filter shape `OrderInquiryWorklistParams` sends
 * to `GET /order-inquiries`, minus `state` - this always means placed rows, whatever
 * else is filtered - and never `product_ids`: the worklist paginates server-side, so a
 * client-derived product list would miss rows behind page 1. Every field omitted means
 * every placed row in the company.
 */
export interface UnplaceAllRequest {
  query?: string;
  delivery_month?: string;
  raised_date?: string;
  project_id?: string;
  supplier_id?: string;
  raised_by?: string;
}

export interface UnplaceAllResult {
  unplaced: number;
}

/**
 * `POST .../order-inquiry-rows/{rowId}/unplace` - Unlink. With a `link_id` it removes
 * THAT link and leaves the rest; without one it removes every link the row holds, which
 * is what the old whole-row untag meant and what "Unlink all" on a row still means.
 */
export interface UnlinkRequest {
  link_id?: string;
}

/**
 * `GET .../order-inquiries/unplace-all-preview` - the confirm dialog's own numbers,
 * resolved server-side against the SAME filters `unplace-all` itself reads, never off
 * whatever page happens to be loaded. `product_code`/`product_name` are set only when
 * EVERY matching row resolves to the same product.
 */
export interface UnplaceAllPreview {
  count: number;
  product_code?: string | null;
  product_name?: string | null;
}

/* ----------------------------------------------------------- the PO popup
 *
 * `GET {BASE}/order-inquiries/po/{po_id}` - the "PO no" cell's popover (the captain,
 * 20 Aug). Gated the same as the worklist's own read (`projects.projects.view`), never
 * `scm.dashboard.view` - purchasing works this worklist off project permissions, so it
 * never calls the SCM purchase-orders route.
 */

/** One line of the purchase order behind a placed worklist row. Read straight off the
 * line's own balance - never netted against other rows' claims, which is a different
 * reading that belongs to the "Place on PO" candidates. */
export interface OrderInquiryPoDetailLine {
  sku?: string | null;
  product_name?: string | null;
  qty_ordered: string;
  qty_received: string;
  remaining: string;
  location?: string | null;
}

export interface OrderInquiryPoDetail {
  id: string;
  po_number: string;
  supplier_code?: string | null;
  supplier_name?: string | null;
  expected_date?: string | null;
  status: string;
  lines: OrderInquiryPoDetailLine[];
}
