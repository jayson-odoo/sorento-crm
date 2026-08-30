import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import SpecWorkbench from './components/SpecWorkbench';

export const metadata: Metadata = {
  title: 'Product Specifications',
  description: 'Derived product specifications and the spec-search preview.',
};

export default async function ProductSpecificationsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Product Specifications" />
      </Container>

      <Container>
        <SpecWorkbench />
      </Container>
    </>
  );
}
