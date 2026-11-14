export type ServiceJobStatus =
  | 'proposed'
  | 'confirmed'
  | 'on_the_way'
  | 'arrived'
  | 'completed'
  | 'verified'
  | 'cancelled';

export interface ServiceJob {
  id: string;
  job_number: string;
  /** The optional related complaint: a plain reference. */
  complaint_id: string | null;
  complaint_number: string | null;
  customer_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  contact_phone_display?: string | null;
  city: string | null;
  site_address_line1?: string | null;
  site_address_line2?: string | null;
  site_postcode?: string | null;
  site_state?: string | null;
  site_country?: string | null;
  problem: string | null;
  status: ServiceJobStatus;
  status_label: string;
  status_color?: string | null;
  technician_id: string | null;
  technician_name: string | null;
  scheduled_from: string | null;
  scheduled_to: string | null;
  customer_agreed_by: string | null;
  rejection_reason?: string | null;
  cancel_reason?: string | null;
  arrived_at?: string | null;
  completed_at?: string | null;
  verified_at?: string | null;
  created_at?: string | null;
  /** List rows only: covered | partly_covered | not_covered | unknown, null with no products. */
  warranty_summary?: string | null;
  /** The job page only: per product line, with the verdict of each policy term. */
  warranty?: WarrantyLine[];
}

export interface WarrantyVerdict {
  part_name: string | null;
  verdict: string;
  expiry: string | null;
  reason: string;
  is_lifetime: boolean;
  installation_included: boolean;
  policy_version: string | null;
}

export interface WarrantyLine {
  id: string;
  product_code: string | null;
  product_name: string | null;
  kind_name: string | null;
  purchase_date: string | null;
  defect_label: string | null;
  verdicts: WarrantyVerdict[];
}

export interface ServiceJobProduct {
  id: string;
  product_id: string;
  product_code: string | null;
  product_name: string | null;
  kind_id: string | null;
  kind_name: string | null;
  purchase_date: string | null;
  defect_type_id: string | null;
  defect_label: string | null;
}

export interface ServiceJobProductValues {
  product_id: string;
  kind_id: string | null;
  purchase_date: string | null;
  defect_type_id: string | null;
}

export interface CatalogueProduct {
  id: string;
  product_code: string;
  product_name: string;
}

/** What the Create / Edit dialog sends (E.164 phone). */
export interface ServiceJobFormValues {
  customer_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  site_address_line1: string | null;
  site_address_line2: string | null;
  site_postcode: string | null;
  site_city: string | null;
  site_state: string | null;
  site_country: string | null;
  problem: string | null;
  complaint_id: string | null;
}

export interface ConfirmJobValues {
  scheduled_from: string;
  scheduled_to: string | null;
  customer_agreed_by: string;
}

export interface TransitionValues {
  to: ServiceJobStatus;
  reason?: string;
}

export interface BoardColumn {
  technician_id: string | null;
  technician_name: string;
  jobs: ServiceJob[];
}

export interface DispatchBoard {
  day: string;
  waiting: ServiceJob[];
  columns: BoardColumn[];
}
