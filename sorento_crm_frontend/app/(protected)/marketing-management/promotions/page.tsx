import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PromotionsList from './components/PromotionsList';

export const metadata: Metadata = {
  title: 'Promotions',
  description: 'Manage promotions.',
};

export default async function PromotionsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Promotions" />
      </Container>

      <Container>
        <PromotionsList />
      </Container>
    </>
  );
}
