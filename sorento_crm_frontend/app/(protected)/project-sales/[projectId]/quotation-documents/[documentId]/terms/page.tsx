import { Metadata } from 'next';
import { QuotationTermsTab } from '../components/QuotationDocumentTabPanels';

export const metadata: Metadata = {
  title: 'Quotation terms and conditions',
  description: 'The clauses the customer holds us to.',
};

export default function ProjectQuotationTermsPage() {
  return <QuotationTermsTab />;
}
