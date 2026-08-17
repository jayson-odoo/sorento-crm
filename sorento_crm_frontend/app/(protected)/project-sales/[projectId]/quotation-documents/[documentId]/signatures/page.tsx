import { Metadata } from 'next';
import { QuotationSignaturesTab } from '../components/QuotationDocumentTabPanels';

export const metadata: Metadata = {
  title: 'Quotation signatures',
  description: 'Ours on the quotation, and the customer counter-signature on the issued copy.',
};

export default function ProjectQuotationSignaturesPage() {
  return <QuotationSignaturesTab />;
}
