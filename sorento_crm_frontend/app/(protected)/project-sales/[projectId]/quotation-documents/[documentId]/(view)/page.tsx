import { Metadata } from 'next';
import { QuotationHeaderTab } from '../components/QuotationDocumentTabPanels';

export const metadata: Metadata = {
  title: 'Quotation header',
  description: 'Who the quotation is to, its references, its date and its total.',
};

/**
 * The default tab: Header, first of the five (#1341, owner: "i need this to be under 'Header' tab
 * to align with our system design"). The tab strip and the actions come from the layout, so this
 * route is only the panel under them.
 */
export default function ProjectQuotationHeaderPage() {
  return <QuotationHeaderTab />;
}
