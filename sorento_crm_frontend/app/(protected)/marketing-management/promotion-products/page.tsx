import { Metadata } from 'next';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import PromotionProductsList from './components/PromotionProductsList';

export const metadata: Metadata = {
  title: 'Promotion Products',
  description: 'Manage products in promotions.',
};

export default async function PromotionProductsPage() {
  return (
    <>
      <Container>
        <PageHeader title="Promotion Products" />
      </Container>

      <Container>
        <PromotionProductsList />
      </Container>
    </>
  );
}
