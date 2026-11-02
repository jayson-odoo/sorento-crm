import { Metadata } from 'next';
import { QuotationFeedbackPanel } from '../../components/QuotationFeedbackPanel';

export const metadata: Metadata = {
  title: 'Quotation customer feedback',
  description: 'The notes the customer left on the sign link, each ticked off once handled.',
};

/** The Customer feedback tab (PS-QUOTE-MATRIX R20): a route like the other tabs. */
export default function ProjectQuotationFeedbackPage() {
  return <QuotationFeedbackPanel />;
}
