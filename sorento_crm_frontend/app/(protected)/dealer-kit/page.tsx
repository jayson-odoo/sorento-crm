import { Metadata } from 'next';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';

import { PagesList } from './components/PagesList';

export const metadata: Metadata = {
  title: 'Catalogue Pages',
  description: 'Build, publish and version the digital catalogue.',
};

export default function DealerKitPagesPage() {
  return (
    <Container width="fluid">
      <PageHeader title="Catalogue Pages" />

      <PagesList />
    </Container>
  );
}
