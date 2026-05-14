export interface PickingLine {
  id: string;
  picking_header_id: string;
  spo_allocation_id?: string | null;
  product_id: string;
  quantity_expected: number;
  quantity_picked: number;
  quantity_discrepancy: number;
  uom_id?: string | null;
  picked_condition: string;
  condition_remarks?: string | null;
  batch_number_picked?: string | null;
  expiry_date?: Date | null;
  unit_cost?: number | null;
  line_total?: number | null;
  source_warehouse_id?: string | null;
  destination_warehouse_id?: string | null;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  spo_allocation?: {
    id: string;
    spo_number?: string | null;
    spo_line_number?: number | null;
    inbound_shipment_id?: string;
    inbound_shipment?: {
      id: string;
      shipment_number: string | null;
    };
  };
  source_warehouse?: {
    id: string;
    warehouse_code: string;
    warehouse_name: string;
  } | null;
  destination_warehouse?: {
    id: string;
    warehouse_code: string;
    warehouse_name: string;
  } | null;
}

export interface GRN {
  id: string;
  picking_number: string;
  spo_number?: string | null;
  picking_type: string;
  source_entity_type?: string | null;
  source_entity_id?: string | null;
  picking_date: Date;
  picked_by_user_id?: string | null;
  inspection_status: string;
  quality_remarks?: string | null;
  inspected_by_user_id?: string | null;
  inspection_date?: Date | null;
  picking_status: string;
  total_items_picked?: number | null;
  total_items_discrepancy?: number | null;
  total_cost?: number | null;
  notes?: string | null;
  created_at: Date;
  updated_at: Date;
  lines_count?: number;
}

export interface GRNDetail extends GRN {
  picking_lines?: PickingLine[];
}

export interface GRNFormData {
  picking_number: string;
  /** Use null on update to clear the server value (JSON null); omit/undefined skips the field. */
  spo_number?: string | null;
  source_entity_type?: string;
  source_entity_id?: string;
  /** Date or ISO date string (form inputs use string). */
  picking_date: Date | string;
  picked_by_user_id?: string;
  inspection_status: string;
  quality_remarks?: string;
  inspected_by_user_id?: string;
  inspection_date?: Date | string;
  picking_status: string;
  total_items_picked?: number;
  total_items_discrepancy?: number;
  total_cost?: number;
  notes?: string;
  picking_lines?: Array<{
    spo_allocation_id?: string;
    product_id: string;
    quantity_expected: number;
    quantity_picked: number;
    uom_id?: string;
    picked_condition?: string;
    condition_remarks?: string;
    batch_number_picked?: string;
    expiry_date?: Date;
    unit_cost?: number;
    line_total?: number;
    source_warehouse_id?: string;
    destination_warehouse_id?: string;
  }>;
}
