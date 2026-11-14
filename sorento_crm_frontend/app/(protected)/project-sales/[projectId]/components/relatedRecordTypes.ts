/**
 * PROJECT-RELATED-RECORDS: the record types the project's Related tab can show, by `kind`
 * (the backend registry's `project_related_records.RELATED_TYPES` keys).
 *
 * Adding a type is one entry here and one backend registration (AC-D1): the panel reads the
 * label and the record's own page from this map and nothing else, so it never changes.
 */
import { complaintStatusLabel, complaintStatusPillClass } from '@/lib/complaint-status';
import { statusPillClass } from '@/lib/status-pill';
import { ocnStatusPillKey, ocnStatusWord } from '@/types/orderChangeNotice';

/** The retired Sponsorship Form tab; its old links open Related, filtered to sponsorship forms. */
export const LEGACY_SPONSORSHIP_TAB = 'sponsorships';

export interface RelatedRecordTypeDef {
  label: string;
  href: (id: string) => string;
  /** The type's own status words and pill colours, where it has them; else the shared ones. */
  statusLabel?: (status: string) => string;
  statusPillClass?: (status: string) => string;
}

export const RELATED_RECORD_TYPES: Record<string, RelatedRecordTypeDef> = {
  stock_inquiry: {
    label: 'Stock Inquiry',
    href: (id) => `/procurement-management/stock-inquiries/${id}`,
  },
  complaint: {
    label: 'Complaint',
    href: (id) => `/complaint-management/complaints/${id}`,
    // As the complaint's own page reads it ("Appealed", "Processed by CS").
    statusLabel: complaintStatusLabel,
    statusPillClass: complaintStatusPillClass,
  },
  purchase_request: {
    label: 'Purchase request',
    href: (id) => `/procurement-management/purchase-requests/${id}`,
  },
  sponsorship_form: {
    label: 'Sponsorship form',
    href: (id) => `/procurement-management/sponsorship-forms/${id}`,
  },
  new_product_application: {
    label: 'New product application',
    href: (id) => `/procurement-management/new-product-applications/${id}`,
  },
  order_change_notice: {
    label: 'Order change notice',
    href: (id) => `/procurement-management/order-change-notices/${id}`,
    // As the notice's own page reads it ("Done", never "processed_by_cs").
    statusLabel: (status) => ocnStatusWord({ status, approval_status: null }),
    statusPillClass: (status) => statusPillClass(ocnStatusPillKey({ status, approval_status: null })),
  },
};

export function registerRelatedRecordType(kind: string, def: RelatedRecordTypeDef): void {
  RELATED_RECORD_TYPES[kind] = def;
}
