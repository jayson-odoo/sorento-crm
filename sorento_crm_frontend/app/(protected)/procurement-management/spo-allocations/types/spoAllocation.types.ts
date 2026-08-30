export interface SPOAllocation {
  id: string;
  spo_number?: string | null;
  spo_line_number?: number | null;
  /** Null until a container is booked: an imported SPO document has no shipment yet. */
  inbound_shipment_id?: string | null;
  /** Null where the book names a stock location we do not hold; `location_code` keeps it. */
  warehouse_id?: string | null;
  /** The stock location exactly as the book spelled it, held or not. */
  location_code?: string | null;
  storage_zone_id?: string | null;
  allocated_quantity: number;
  uom_id?: string | null;
  receipt_status: string;
  quantity_received: number;
  quantity_rejected: number;
  allocation_notes?: string | null;
  created_at: Date;
  created_by?: string | null;
  product_id: string;
  synced_to_excel: boolean;
  updated_at?: Date | null;
  last_synced_to_excel?: Date | null;
  inbound_shipment?: {
    id: string;
    shipment_number: string | null;
    shipping_container_number?: string | null;
  };
  warehouse?: {
    id: string;
    warehouse_code: string;
    warehouse_name: string;
  };
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  grn_lines_count?: number;
  /** GRN headers linked to this SPO (same spo_number); for quick navigation. */
  linked_grns?: LinkedGRNSimple[];
  /** Which feed wrote the row; null for one this system raised itself. */
  source_system?: string | null;
  /** `open` / `closed`, the same word a purchase-order line carries. */
  line_status?: string | null;
  /** The SPO's document date, and the line's promised arrival. */
  issue_date?: string | null;
  expected_date?: string | null;
  supplier_id?: string | null;
  unit_cost?: number | string | null;
  currency?: string | null;
}

export interface LinkedGRNSimple {
  id: string;
  picking_number?: string | null;
  picking_status?: string | null;
  picking_date?: string | null;
}

export interface SPOAllocationDetail extends SPOAllocation {}

/** Shipment line (packing list line) with product and quantity shipped. */
export interface ShipmentLineForGroup {
  id: string;
  product_id: string;
  quantity_shipped: number;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
}

/** Inbound shipment with its SPO allocations and shipment lines (grouped list view). */
export interface ShipmentWithAllocationsGroup {
  inbound_shipment: {
    id: string;
    shipment_number: string | null;
    shipping_container_number?: string | null;
  };
  spo_allocations: SPOAllocation[];
  shipment_lines?: ShipmentLineForGroup[] | null;
}

/** SPO allocation with quantity_shipped from packing list. */
export interface SPOAllocationWithShipped extends SPOAllocation {
  quantity_shipped?: number | null;
}

/** SPO number with its allocations (grouped list view by SPO). */
export interface SPOWithAllocationsGroup {
  spo_number: string;
  spo_allocations: SPOAllocationWithShipped[];
}

export interface SPOAllocationFormData {
  spo_number?: string;
  spo_line_number?: number;
  inbound_shipment_id: string;
  warehouse_id: string;
  storage_zone_id?: string;
  allocated_quantity: number;
  uom_id?: string;
  receipt_status: string;
  quantity_received?: number;
  quantity_rejected?: number;
  allocation_notes?: string;
  product_id: string;
}
