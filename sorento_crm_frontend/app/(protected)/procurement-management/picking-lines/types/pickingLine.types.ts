export interface PickingLineListItem {
  id: string;
  picking_header_id: string;
  spo_allocation_id?: string | null;
  product_id: string;
  quantity_expected: number;
  quantity_picked: number;
  quantity_discrepancy: number;
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

export interface PickingLinesListResponse {
  data: PickingLineListItem[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}
