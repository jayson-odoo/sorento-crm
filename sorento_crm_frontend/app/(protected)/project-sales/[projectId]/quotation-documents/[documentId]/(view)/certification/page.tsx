'use client';

import { QuotationCertificatesList } from '../../components/QuotationCertificatesList';
import { useQuotationDocumentScreen } from '../../components/QuotationDocumentContext';

export default function ProjectQuotationCertificationPage() {
  const { projectId, documentId } = useQuotationDocumentScreen();
  return <QuotationCertificatesList projectId={projectId} documentId={documentId} />;
}
