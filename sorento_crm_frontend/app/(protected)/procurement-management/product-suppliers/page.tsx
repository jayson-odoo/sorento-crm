import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductSuppliersGrid from './components/ProductSuppliersGrid';

export const metadata: Metadata = {
  title: 'Product Suppliers',
  description: 'Manage product supplier relationships.',
};

export default async function ProductSuppliersPage() {
  return (
    <>
      <Container>
        <PageHeader title="Product Suppliers" />
      </Container>

      <Container>
        <ProductSuppliersGrid />
      </Container>
    </>
  );
}
