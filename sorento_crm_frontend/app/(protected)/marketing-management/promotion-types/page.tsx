import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PromotionTypesList from './components/PromotionTypesList';

export const metadata: Metadata = {
  title: 'Promotion Types',
  description: 'Promotion types and what happens to each after it expires.',
};

export default async function PromotionTypesPage() {
  return (
    <>
      <Container>
        <PageHeader title="Promotion Types" />
      </Container>

      <Container>
        <PromotionTypesList />
      </Container>
    </>
  );
}
