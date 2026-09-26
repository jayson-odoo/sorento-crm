import { Metadata } from 'next';
import SalesOpportunitiesView from './components/SalesOpportunitiesView';

export const metadata: Metadata = {
  title: 'Sales Opportunities',
  description: 'Opportunities logged by salespeople and the CRM.',
};

export default function SalesOpportunitiesPage() {
  return <SalesOpportunitiesView />;
}
