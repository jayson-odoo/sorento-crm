export interface ItemPackageLine {
  id: string;
  product_id: string;
  product_code: string | null;
  product_name: string | null;
  line_sequence: number;
  uom: string | null;
  qty: string | number | null;
  unit_price: string | number | null;
}

export interface ItemPackage {
  id: string;
  package_code: string;
  description: string | null;
  expiry_date: string | null;
  limited_qty: string | number | null;
  opening_qty: string | number | null;
  user_uom: string | null;
  bar_code: string | null;
  further_description: string | null;
  is_active: boolean;
  internal_note: string | null;
  follow_up: boolean;
  source: 'autocount' | 'manual';
  created_at: string;
  updated_at: string | null;
  lines: ItemPackageLine[];
}

export interface MirrorAnnotationPayload {
  internal_note: string;
  follow_up: boolean;
}
