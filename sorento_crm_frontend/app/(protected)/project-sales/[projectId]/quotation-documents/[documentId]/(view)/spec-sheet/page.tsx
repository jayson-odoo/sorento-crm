import { Metadata } from 'next';
import { QuotationSpecSheetsList } from '../../components/QuotationSpecSheetsList';

export const metadata: Metadata = {
  title: 'Quotation spec sheets',
  description: 'The spec sheets made from this quotation: a cover and one page per quoted item.',
};

export default function ProjectQuotationSpecSheetPage() {
  return <QuotationSpecSheetsList />;
}
