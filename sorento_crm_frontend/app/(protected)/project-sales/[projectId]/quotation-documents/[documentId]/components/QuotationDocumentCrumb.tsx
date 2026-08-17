'use client';

import { BreadcrumbPage } from '@/components/ui/breadcrumb';
import { useQuotationDocument } from '../../../../_shared/hooks/useQuotationDocuments';

/**
 * The last crumb: the document NUMBER, not the id in the URL (no UUIDs in the UI).
 *
 * It reads the same cached query the screen below it uses, so naming the crumb costs no extra
 * request; "Quotation" stands in only for the moment before that query answers.
 */
export function QuotationDocumentCrumb({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const document = useQuotationDocument(projectId, documentId);
  return <BreadcrumbPage>{document.data?.document_no ?? 'Quotation'}</BreadcrumbPage>;
}
