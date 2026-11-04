import type { BillingDocumentType } from '@/app/(protected)/finance/billing-documents/types/billingDocument.types';

/** The record a Related table hangs off (DOC-RELATIONS). */
export type RelatedAnchorKind =
  | 'sales_order'
  | 'delivery_order'
  | 'billing_document';

export type RelatedRowType =
  | 'sales_order'
  | 'delivery_order'
  | BillingDocumentType;

export interface RelatedRow {
  kind: RelatedAnchorKind;
  type: RelatedRowType;
  /** Null for a delivery order a billing document names that the CRM does not hold. */
  id: string | null;
  doc_no: string;
  /** A sales order row's customer (debtor name, else customer master) and project label. */
  customer_name?: string | null;
  project_label?: string | null;
  /** YYYY-MM-DD */
  doc_date: string | null;
  status: string | null;
  amount: number | null;
  currency_code: string | null;
}

export type RelatedSortKey =
  | 'type'
  | 'doc_no'
  | 'customer_name'
  | 'project_label'
  | 'doc_date'
  | 'status'
  | 'amount';

export interface RelatedDocumentsResponse {
  /** Each kind is null when the viewer lacks its view slug (the server masks it). */
  sales_orders: unknown[] | null;
  delivery_orders: unknown[] | null;
  billing_documents: unknown[] | null;
  /** The visible kinds as one table, in the order the server sorted it. */
  rows: RelatedRow[];
}
