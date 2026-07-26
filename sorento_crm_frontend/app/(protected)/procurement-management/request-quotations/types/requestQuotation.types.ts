export interface RequestQuotationLine {
  id: string;
  product_id: string | null;
  product_code: string | null;
  product_name: string | null;
  line_sequence: number;
  uom: string | null;
  location: string | null;
  qty: string | number | null;
  unit_price: string | number | null;
  sub_total: string | number | null;
}

export interface RequestQuotation {
  id: string;
  rq_number: string;
  source_doc_no: string | null;
  supplier_id: string | null;
  supplier_code: string | null;
  supplier_name: string | null;
  creditor_code: string | null;
  creditor_name: string | null;
  doc_date: string | null;
  purchase_agent: string | null;
  internal_note: string | null;
  follow_up: boolean;
  source: 'autocount' | 'manual';
  created_at: string;
  updated_at: string | null;
  lines: RequestQuotationLine[];
}

export interface MirrorAnnotationPayload {
  internal_note: string;
  follow_up: boolean;
}
