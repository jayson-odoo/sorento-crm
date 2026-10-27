/**
 * DOC-RELATIONS - the Related table's feature service.
 *
 * Layering: RelatedDocumentsPanel -> useRelatedDocuments -> THIS service -> lib/api.
 *
 * Backend contract (be/app/services/document_relations.py), one route per record, each behind
 * that record's own view slug; `sort` is one of type, doc_no, doc_date, status, amount:
 *   GET /scm/sales-orders/{id}/related?sort=&dir=            scm.dashboard.view
 *   GET /order-management/orders/{id}/related?sort=&dir=     order_management.orders.view
 *   GET /finance/billing-documents/{id}/related?sort=&dir=   finance.billing_documents.view
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  RelatedAnchorKind,
  RelatedDocumentsResponse,
  RelatedSortKey,
} from './relatedDocuments.types';

const PATHS: Record<RelatedAnchorKind, (id: string) => string> = {
  sales_order: (id) => `/api/v1/scm/sales-orders/${id}/related`,
  delivery_order: (id) => `/api/v1/order-management/orders/${id}/related`,
  billing_document: (id) => `/api/v1/finance/billing-documents/${id}/related`,
};

export async function getRelatedDocuments(
  kind: RelatedAnchorKind,
  id: string,
  sort: RelatedSortKey,
  dir: 'asc' | 'desc',
): Promise<RelatedDocumentsResponse> {
  const usp = new URLSearchParams({ sort, dir });
  const response = await apiFetch(`${PATHS[kind](id)}?${usp.toString()}`);
  if (!response.ok)
    throw new Error(
      await extractApiError(response, 'Failed to load related documents'),
    );
  return response.json();
}
