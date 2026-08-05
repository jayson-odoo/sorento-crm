import { Metadata } from 'next';
import { QuotationCoverLetterTab } from '../components/QuotationDocumentTabPanels';

export const metadata: Metadata = {
  title: 'Quotation cover letter',
  description: 'The letter the customer reads before the prices.',
};

export default function ProjectQuotationCoverLetterPage() {
  return <QuotationCoverLetterTab />;
}
