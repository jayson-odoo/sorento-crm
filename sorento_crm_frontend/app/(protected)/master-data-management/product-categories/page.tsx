import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import CategoriesList from './components/CategoriesList';

export const metadata: Metadata = {
  title: 'Product Categories',
  description: 'Manage product categories.',
};

export default async function ProductCategoriesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Product Categories" />
      </Container>

      <Container>
        <CategoriesList />
      </Container>
    </>
  );
}
