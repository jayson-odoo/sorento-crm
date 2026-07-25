import { Metadata } from 'next';

import { IntegrationDetailView } from '../components/IntegrationDetailView';

export const metadata: Metadata = {
  title: 'Integration',
  description: 'Integration configuration and API keys.',
};

export default async function IntegrationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <IntegrationDetailView id={id} />;
}
