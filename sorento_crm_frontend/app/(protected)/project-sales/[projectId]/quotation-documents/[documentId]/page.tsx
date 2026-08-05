import { Metadata } from 'next';
import { QuotationScopesTab } from './components/QuotationScopesTab';

export const metadata: Metadata = {
  title: 'Quotation scopes',
  description: 'The parts of the development priced under this quotation.',
};

/**
 * The default tab: the scopes and their priced lines. The letterhead, the tab strip and the
 * actions come from the layout, so this route is only the panel under them.
 */
export default function ProjectQuotationScopesPage() {
  return <QuotationScopesTab />;
}
