import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { CollectionsList } from './components/CollectionsList';

export const metadata: Metadata = {
  title: 'Product Collections',
  description: 'Reusable product sets that several catalogue pages can share.',
};

export default function DealerKitCollectionsPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Product Collections" />

      <CollectionsList />
    </Container>
  );
}
