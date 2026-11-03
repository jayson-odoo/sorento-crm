import { Metadata } from 'next';
import { QuotationSpecSheetTab } from '../../components/QuotationSpecSheetTab';

export const metadata: Metadata = {
  title: 'Quotation spec sheet',
  description: 'The project catalogue: a cover and one page per quoted item.',
};

export default function ProjectQuotationSpecSheetPage() {
  return <QuotationSpecSheetTab />;
}
