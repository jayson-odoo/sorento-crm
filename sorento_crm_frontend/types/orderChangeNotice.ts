/**
 * Order Change Notice (OCN-ORDER-CHANGE-NOTICE): the shapes of
 * `/api/v1/procurement/order-change-notices`. The backend answers flat rows
 * (`app/services/order_change_notice_service.py` `serialize_summary` / `serialize_detail`).
 */

export type OcnStatus =
  | 'draft'
  | 'submitted'
  | 'resubmitted'
  | 'approved'
  | 'rejected'
  | 'processed_by_cs'
  | 'voided';

export interface OcnChangeType {
  id: string;
  name: string;
  risk_level: string;
  guide_text?: string | null;
  is_active?: boolean;
}

export interface OcnLine {
  id?: string;
  position?: number;
  product_id: string;
  product_code?: string | null;
  product_name?: string | null;
  qty_before?: string | null;
  qty_after?: string | null;
  date_before?: string | null;
  date_after?: string | null;
  delivered_qty?: string | null;
  remark?: string | null;
}

export interface OcnRow {
  id: string;
  ocn_number: string;
  ocn_date?: string | null;
  status: OcnStatus | string;
  approval_status?: string | null;
  revision_no?: number | null;
  source?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  customer_po_no?: string | null;
  so_no_text?: string | null;
  change_type_id?: string | null;
  change_type_name?: string | null;
  risk_level?: string | null;
  project_id?: string | null;
  project_title?: string | null;
  sales_in_charge_user_id?: string | null;
  sales_in_charge_name?: string | null;
  cs_in_charge_user_id?: string | null;
  cs_in_charge_name?: string | null;
  created_at?: string | null;
}

export interface OcnDetail extends OcnRow {
  guide_text?: string | null;
  description?: string | null;
  cs_comment?: string | null;
  reason?: string | null;
  project_sales_order_id?: string | null;
  purchase_order_id?: string | null;
  created_by?: string | null;
  created_by_name?: string | null;
  submitted_at?: string | null;
  approver_id?: string | null;
  approver_name?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
  approval_comments?: string | null;
  rejected_by_name?: string | null;
  voided_by_name?: string | null;
  voided_at?: string | null;
  void_reason?: string | null;
  lines: OcnLine[];
  /** An amendment-born or picked notice: the amendment's change table (rows, verb summary). */
  change_table_json?: {
    rows?: unknown[];
    verb_summary?: Record<string, number>;
    unmatched?: unknown[];
  } | null;
  so_ref?: string | null;
  po_number?: string | null;
  amendment_id?: string | null;
  amendment_status?: string | null;
  amendment_sales_order_id?: string | null;
  attachments?: OcnAttachment[];
}

export interface OcnAttachment {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  content_type?: string | null;
  uploaded_at?: string | null;
}

export interface OcnLineInput {
  product_id: string;
  qty_before?: string | null;
  qty_after?: string | null;
  date_before?: string | null;
  date_after?: string | null;
  delivered_qty?: string | null;
  remark?: string | null;
}

/** The create / edit body (the backend's `OrderChangeNoticeWrite`). */
export interface OcnWrite {
  change_type_id?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  customer_po_no?: string | null;
  so_no_text?: string | null;
  project_id?: string | null;
  sales_in_charge_user_id?: string | null;
  cs_in_charge_user_id?: string | null;
  description?: string | null;
  ocn_date?: string | null;
  lines?: OcnLineInput[];
}

export interface OcnPage {
  data: OcnRow[];
  pagination: { total: number; page: number; limit: number };
  empty?: boolean;
}

export interface OcnProductHit {
  id: string;
  product_code: string;
  product_name: string;
  brand_name?: string | null;
}

export const OCN_STATUS_WORDS: Record<string, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  // One word on every form (submission_status: "Appealed"), the backend's label too.
  resubmitted: 'Appealed',
  approved: 'Approved',
  rejected: 'Rejected',
  processed_by_cs: 'Done',
  voided: 'Voided',
};

/** The approval decision in words, as the sign-off reads it ("Pending" until a decision). */
export const OCN_APPROVAL_WORDS: Record<string, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  voided: 'Voided',
};

/** The status in plain words: a submitted notice waiting on its approver reads "Pending approval". */
export function ocnStatusWord(row: Pick<OcnRow, 'status' | 'approval_status'>): string {
  const status = String(row.status ?? '');
  if ((status === 'submitted' || status === 'resubmitted') && row.approval_status === 'pending') {
    return 'Pending approval';
  }
  return OCN_STATUS_WORDS[status] ?? (status ? status.replace(/_/g, ' ') : '-');
}

/** The key the status pill colours by: pending approval reads as pending. */
export function ocnStatusPillKey(row: Pick<OcnRow, 'status' | 'approval_status'>): string {
  const word = ocnStatusWord(row);
  if (word === 'Pending approval') return 'pending_approval';
  if (row.status === 'processed_by_cs') return 'completed';
  return String(row.status ?? '');
}

/** An amendment-born notice carrying the amendment's change rows: the rows are its lines, and
 *  Submit asks for no typed customer, PO or line (the backend's `validate_submit`). */
export function carriesChangeRows(row: Pick<OcnDetail, 'source' | 'change_table_json'> | null | undefined): boolean {
  return Boolean(row && row.source === 'amendment' && (row.change_table_json?.rows?.length ?? 0) > 0);
}

/** The backend's edit rule (`_assert_may_edit`), one place for every button that needs it
 *  (Edit, Void, the files): `.edit` acts on any notice, the raiser acts on their own while they
 *  hold `.create`. */
export function mayEditNotice({ mine, canCreate, canEdit }: { mine: boolean; canCreate: boolean; canEdit: boolean }): boolean {
  return canEdit || (mine && canCreate);
}

export const OCN_SOURCE_WORDS: Record<string, string> = { crm: 'CRM', amendment: 'Amendment' };
