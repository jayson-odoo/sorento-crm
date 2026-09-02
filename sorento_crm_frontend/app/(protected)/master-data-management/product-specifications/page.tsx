'use client';

import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SpecRegistryPage } from './components/SpecRegistryPage';

export default function ProductSpecificationsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Product Specifications" />
      </Container>

      <Container>
        <SpecRegistryPage />
      </Container>
    </>
  );
}
