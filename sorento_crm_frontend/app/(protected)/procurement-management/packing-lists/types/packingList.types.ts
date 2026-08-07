export interface InboundShipmentLine {
  id: string;
  shipment_id: string;
  product_id: string;
  quantity_shipped: number;
  uom_id?: string | null;
  batch_number?: string | null;
  serial_number_range_from?: string | null;
  serial_number_range_to?: string | null;
  carton_number?: string | null;
  cartons_count: number;
  weight_per_carton?: number | null;
  unit_cost?: number | null;
  /** Total SPO allocated quantity for this product on this shipment (all warehouses). */
  spo_allocated_quantity?: number | null;
  /** Sum of quantity_received from SPO allocations for this line. */
  quantity_received?: number | null;
  /** Stored in DB: in_transit, allocated, partially_allocated, received, partially_received (for n8n/API). */
  line_status?: string | null;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  related_spo_allocations?: Array<{
    id: string;
    spo_number?: string | null;
    allocated_quantity?: number | null;
    receipt_status?: string | null;
  }>;
  related_grns?: Array<{
    id: string;
    picking_number?: string | null;
    spo_number?: string | null;
    picking_status?: string | null;
    picking_date?: string | Date | null;
  }>;
}

export interface PackingList extends ClearanceFields {
  id: string;
  shipment_number: string | null;
  supplier_id: string;
  shipment_date: Date;
  estimated_arrival_date?: Date | null;
  actual_arrival_date?: Date | null;
  bill_of_lading_number?: string | null;
  shipping_container_number?: string | null;
  invoice_number?: string | null;
  shipment_status: string;
  total_items_shipped?: number | null;
  total_cartons?: number | null;
  notes?: string | null;
  created_at: Date;
  created_by?: string | null;
  updated_at: Date;
  attachment_id?: string | null;
  synced_to_excel: boolean;
  last_synced_to_excel?: Date | null;
  supplier?: {
    id: string;
    supplier_code: string;
    supplier_name: string;
  };
  attachment?: {
    id: string;
    original_filename: string;
    stored_filename: string;
    file_path: string;
    file_size_bytes: number | null;
    mime_type: string | null;
    attachment_type?: {
      id: string;
      type_name: string;
    } | null;
  } | null;
  lines_count?: number;
  spo_allocations_count?: number;
  display_total_items?: number | null;
  display_total_cartons?: number | null;
}

/**
 * Container-status clearance fields.
 *
 * PHASE 1 CONTRACT (mocked). These arrive on the same `inbound_shipments` row as
 * the packing list: one Container Status sheet row = one packing list. Every field
 * is optional because a caller without entitlement receives the keys **absent**,
 * not null - absent means "you may not see this", null means "not reached yet".
 * See documentation/plans/purchasing/container-status-tracking-acceptance-criteria.md
 * sections B and C.
 */
export interface ClearanceFields {
  /** Yard / warehouse location code (sheet column LOC). */
  loc?: string | null;
  liner_code?: string | null;
  china_forwarder?: string | null;
  malaysia_forwarder?: string | null;
  consignee?: string | null;
  /** Free days before demurrage / detention starts. */
  free_days_available?: number | null;
  stacked?: string | null;

  loading_date?: string | null;
  etc_date?: string | null;
  etd_date?: string | null;
  /** First-published ETA. */
  /** Revised ETA - the accurate one. Doubles as de-facto arrival. */
  eta_delay_date?: string | null;
  inspection_date?: string | null;
  approval_date?: string | null;
  gatepass_date?: string | null;
  delivery_warehouse?: string | null;
  warehouse_arrival_date?: string | null;
  informed_collection_date?: string | null;
  collection_date?: string | null;

  /*
   * ATA, ORI DOC RECEIVED, K1 SUBMISSION and YARD ARRIVALS are deliberately absent.
   * They exist on the sheet but are filled 6 / 4 / 4 / 4 times across 407
   * containers and nothing reads them, so they are not columns, not imported and
   * not shown. The retained source file keeps the history (D34).
   */

  coa_permit_no?: string | null;
  /** Which workbook tab the row came from. Traceability only - never derives status. */
  source_sheet?: string | null;
}

export interface PackingListDetail extends PackingList {
  shipment_lines?: InboundShipmentLine[];
}

export interface PackingListFormData {
  shipment_number?: string | null;
  supplier_id?: string;
  shipment_date: string;
  estimated_arrival_date?: string;
  actual_arrival_date?: string;
  bill_of_lading_number?: string;
  shipping_container_number?: string;
  invoice_number?: string;
  shipment_status?: string;
  total_items_shipped?: number;
  total_cartons?: number;
  notes?: string;
  attachment_id?: string | null;
  shipment_lines?: Array<{
    product_id: string;
    quantity_shipped: number;
    uom_id?: string;
    batch_number?: string;
    serial_number_range_from?: string;
    serial_number_range_to?: string;
    carton_number?: string;
    cartons_count?: number;
    weight_per_carton?: number;
    unit_cost?: number;
  }>;
}
