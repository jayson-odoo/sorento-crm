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
  complaint_id: string;
  complaint_number: string | null;
  customer_name: string | null;
  city: string | null;
  site_address_line1?: string | null;
  site_address_line2?: string | null;
  site_postcode?: string | null;
  site_state?: string | null;
  site_country?: string | null;
  site_contact_name?: string | null;
  site_contact_phone?: string | null;
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
