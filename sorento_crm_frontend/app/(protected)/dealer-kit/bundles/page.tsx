import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { BundlesList } from './components/BundlesList';

export const metadata: Metadata = {
  title: 'Bundles',
  description: 'Products sold together under one price.',
};

export default function DealerKitBundlesPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Bundles" />

      <BundlesList />
    </Container>
  );
}
