export interface QuotationLine {
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
  discount_amt: string | number | null;
  tax_code: string | null;
  tax_rate: string | number | null;
  tax: string | number | null;
  description: string | null;
  further_description: string | null;
  package_code: string | null;
  proj_no: string | null;
  dept_no: string | null;
}

export interface Quotation {
  id: string;
  quote_number: string;
  source_doc_no: string | null;
  debtor_code: string | null;
  debtor_name: string | null;
  doc_date: string | null;
  is_cancelled: boolean;
  attention: string | null;
  branch_code: string | null;
  deliver_addr1: string | null;
  deliver_addr2: string | null;
  deliver_addr3: string | null;
  deliver_addr4: string | null;
  terms: string | null;
  sales_agent: string | null;
  internal_note: string | null;
  follow_up: boolean;
  source: 'autocount' | 'manual';
  created_at: string;
  updated_at: string | null;
  lines: QuotationLine[];
}

export interface MirrorAnnotationPayload {
  internal_note: string;
  follow_up: boolean;
}
