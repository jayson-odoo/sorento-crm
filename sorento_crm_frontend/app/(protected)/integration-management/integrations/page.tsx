import { Metadata } from 'next';

import { IntegrationsView } from './components/IntegrationsView';

export const metadata: Metadata = {
  title: 'Integrations',
  description: 'Manage integrations and their API keys.',
};

export default function IntegrationsPage() {
  return <IntegrationsView />;
}
