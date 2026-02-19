export interface SPOAllocation {
  id: string;
  spo_number?: string | null;
  spo_line_number?: number | null;
  inbound_shipment_lines_id?: string | null;
  inbound_shipment_id: string;
  warehouse_id: string;
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
    shipment_number: string;
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
    shipment_number: string;
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
  inbound_shipment_lines_id?: string;
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
