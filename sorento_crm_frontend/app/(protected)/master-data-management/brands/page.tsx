import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BrandsList from './components/BrandsList';

export const metadata: Metadata = {
  title: 'Brands',
  description: 'Manage brands.',
};

export default async function BrandsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Brands" />
      </Container>

      <Container>
        <BrandsList />
      </Container>
    </>
  );
}
