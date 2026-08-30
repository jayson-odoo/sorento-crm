import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { EditionsList } from './components/EditionsList';

export const metadata: Metadata = {
  title: 'Editions',
  description: 'Catalogue revisions waiting to be approved or published.',
};

export default function DealerKitEditionsPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Editions" />

      <EditionsList />
    </Container>
  );
}
