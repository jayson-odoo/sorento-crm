import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductsList from './components/ProductsList';

export const metadata: Metadata = {
  title: 'Products',
  description: 'Manage products.',
};

export default async function ProductsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Products" />
      </Container>

      <Container>
        <ProductsList />
      </Container>
    </>
  );
}
