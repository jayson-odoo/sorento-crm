import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import AccessoriesList from './components/AccessoriesList';

export const metadata: Metadata = {
  title: 'Accessories',
  description: 'Manage accessories.',
};

export default async function AccessoriesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Accessories" />
      </Container>

      <Container>
        <AccessoriesList />
      </Container>
    </>
  );
}
