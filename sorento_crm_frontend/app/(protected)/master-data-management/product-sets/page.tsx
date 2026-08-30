import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import ProductSetsList from './components/ProductSetsList';

export const metadata: Metadata = {
  title: 'Product Sets',
  description: 'The code that names an assembly sold as one thing and stocked as several.',
};

export default async function ProductSetsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Product Sets" />
      </Container>

      <Container>
        <ProductSetsList />
      </Container>
    </>
  );
}
