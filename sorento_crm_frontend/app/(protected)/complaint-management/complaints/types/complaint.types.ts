export interface ComplaintProductLine {
  product_code: string;
  quantity?: string | null;
  product_type?: string | null;
  /** What the consumer actually said, verbatim. `product_code` on a retail line is
   *  frequently a guess: `SRTWC8152` matches three real variants and resolves to none
   *  of them, so this is the only thing an agent can act on when matching fails. */
  claimed_text?: string | null;
  /** Per line, not per complaint: two broken items in one visit are two faults. */
  fault_description?: string | null;
  defect_type_name?: string | null;
  kind_name?: string | null;
  product_name?: string | null;
  purchase_number?: string | null;
  purchase_date?: string | null;
}

export interface ComplaintAttachment {
  id: string;
  complaint_id: string;
  attachment_id?: string | null;
  /** Original filename (from attachment). Prefer this for display. */
  file_name?: string | null;
  original_filename?: string | null;
  file_url?: string | null;
  file_size_bytes?: number | null;
  uploaded_at: Date;
  created_at?: Date;
  /** From complaint_attachments table. 'response_attachment' rows come from the
   *  technical team response popup and unlink through a dedicated endpoint. */
  link_type?: 'complaint_attachment' | 'response_attachment' | null;
  /** Uploader attribution (S1) - names only, never a UUID. */
  uploader_kind?: 'user' | 'contact' | 'system' | null;
  uploaded_by_name?: string | null;
  uploaded_by_role?: 'contact' | 'staff' | null;
}

export interface Complaint {
  id: string;
  complaint_number?: string | null;
  delivery_order_number?: string | null;
  complaint_date?: Date | null;
  customer_type?: string | null;
  customer_type_others?: string | null;
  within_warranty?: string | null;
  product_type?: string | null;
  defects_discovered?: string | null;
  complaint_type?: string | null;
  defect_description?: string | null;
  product_code?: string | null;
  quantity?: string | null;
  salesperson?: string | null;
  customer_name?: string | null;
  contact_person?: string | null;
  contact_number?: string | null;
  customer_address?: string | null;
  project_title?: string | null;
  contact_id?: string | null;
  space_id?: string | null;
  respond_inbox_url?: string | null;
  technical_team_response?: string | null;
  status?: string | null;
  rejection_reason?: string | null;
  /** R3 void audit fields (populated when status === 'voided'). */
  voided_by?: string | null;
  voided_by_name?: string | null;
  voided_at?: string | null;
  void_reason?: string | null;
  last_responded_by?: string | null;
  last_responded_by_name?: string | null;
  last_responded_at?: string | null;
  created_at?: string | null;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  handled_by_name?: string | null;
  root_cause_id?: string | null;
  resolution_id?: string | null;
  root_cause_name?: string | null;
  resolution_name?: string | null;
  root_cause_notified_at?: string | null;
  resolution_notified_at?: string | null;
  required_on_site_support?: boolean | null;
  print_count?: number | null;
  product_lines?: ComplaintProductLine[];
  attachments: ComplaintAttachment[];

  /** Who reported the fault. One of end_user / dealer / salesperson / cs / technician,
   *  or null on the live rows that predate it. The detail screen branches on this. */
  reported_by_role?: string | null;
  /** The Site: whatever was REPORTED, never the dealer's own address. A dealer's owner
   *  reporting a fault in his own home carries a dealer binding and a residential Site
   *  on the same row. `site_address` is the composed line every document prints; the
   *  parts exist so a postcode can be corrected without re-parsing prose. */
  site_address?: string | null;
  site_address_line1?: string | null;
  site_address_line2?: string | null;
  site_postcode?: string | null;
  site_city?: string | null;
  site_state?: string | null;
  site_country?: string | null;
  site_contact_name?: string | null;
  site_contact_phone?: string | null;
  /** The pin a technician navigates to. Never reconciled against the address: the pin
   *  is for navigation, the address for documents. */
  latitude?: number | string | null;
  longitude?: number | string | null;
  /** The WhatsApp intake burst verbatim, in the order sent. What a human reads when the
   *  extraction is wrong. */
  intake_transcript?: string | null;
}

export interface ComplaintFormData {
  delivery_order_number?: string;
  complaint_date?: Date;
  customer_type?: string;
  customer_type_others?: string;
  within_warranty?: string;
  product_type?: string;
  defects_discovered?: string;
  complaint_type?: string;
  defect_description?: string;
  product_code?: string;
  quantity?: string;
  product_lines?: ComplaintProductLine[];
  salesperson?: string;
  customer_name?: string;
  contact_person?: string;
  contact_number?: string;
  customer_address?: string;
  project_title?: string;
  contact_id?: string | null;
  space_id?: string | null;
  technical_team_response?: string;
  status?: string;
  last_responded_by?: string;
  last_responded_at?: string;
  root_cause_id?: string | null;
  resolution_id?: string | null;
  required_on_site_support?: boolean | null;
  attachments?: ComplaintAttachment[];
}

export interface ComplaintDetail extends Complaint {
  attachments: ComplaintAttachment[];
}
