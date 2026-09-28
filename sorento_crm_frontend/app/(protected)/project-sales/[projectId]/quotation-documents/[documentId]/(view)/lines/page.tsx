import { Metadata } from 'next';
import { QuotationScopesTab } from '../../components/QuotationScopesTab';

export const metadata: Metadata = {
  title: 'Quotation lines',
  description: 'The parts of the development priced under this quotation.',
};

/**
 * The Lines tab (#1341: the owner wrote "Lines" over the old Scopes label): the scope strip and
 * the priced lines under whichever scope is open. The data model keeps "scope".
 */
export default function ProjectQuotationLinesPage() {
  return <QuotationScopesTab />;
}
