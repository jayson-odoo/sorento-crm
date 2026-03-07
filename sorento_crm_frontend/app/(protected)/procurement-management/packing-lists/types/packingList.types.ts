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
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
}

export interface PackingList {
  id: string;
  shipment_number: string;
  supplier_id: string;
  shipment_date: Date;
  expected_arrival_date?: Date | null;
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
  attachment_id: string;
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

export interface PackingListDetail extends PackingList {
  shipment_lines?: InboundShipmentLine[];
}

export interface PackingListFormData {
  shipment_number: string;
  supplier_id?: string;
  shipment_date: string;
  expected_arrival_date?: string;
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
